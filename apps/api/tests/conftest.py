"""Pytest fixtures: settings, a real Postgres schema, ASGI client, and JWT minting.

Tests run against a real Postgres (the models use citext/jsonb), pointed at
`TEST_DATABASE_URL` (or a local default). Schema is created once per session;
`users`/`admin_audit` are truncated between tests for isolation.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator

import jwt
import pytest
import pytest_asyncio

# Configure the environment before importing app modules (config reads env).
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test",
)
TEST_JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long!"

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"
os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"
os.environ["ENV"] = "local"
# Mount the demo router. `create_app` only includes it when this is set, and the
# `app` fixture is session-scoped, so without it every /demo/* route 404s no
# matter what a per-test fixture does to the other demo flags -- which is a
# confusing way for a test to fail, because the 404 looks like a rejected flag
# check rather than a route that was never registered.
os.environ["DEMO_LOGIN_ENABLED"] = "1"
# The shared ASGI client fires many writes from one host across a session; keep
# the global limiter out of its way. The limiter itself is proven in
# test_security_middleware.py against a purpose-built low-limit app.
os.environ["RATE_LIMIT_WRITES_PER_MINUTE"] = "100000"
# The PUBG host client throttles to ~9 req/min in prod; keep it out of the way of
# respx-mocked tests (the token bucket itself is proven in test_pubg_rate_limit.py).
os.environ["PUBG_RATE_LIMIT_PER_MIN"] = "100000"

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from moneymatch_api.config import get_settings  # noqa: E402
from moneymatch_api.db.append_only import (  # noqa: E402
    ALL_APPEND_ONLY_TABLES,
    install_statements,
)
from moneymatch_api.db.session import get_engine, get_sessionmaker  # noqa: E402
from moneymatch_api.main import create_app  # noqa: E402
from moneymatch_api.models import Base  # noqa: E402
from moneymatch_api.services.feature_flags import DEFAULT_FLAGS  # noqa: E402


def make_token(
    sub: str,
    *,
    email: str | None = "player@example.com",
    secret: str = TEST_JWT_SECRET,
    audience: str = "authenticated",
    algorithm: str = "HS256",
    exp_offset: int = 3600,
) -> str:
    now = int(time.time())
    payload: dict = {"sub": sub, "aud": audience, "iat": now, "exp": now + exp_offset}
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest_asyncio.fixture(scope="session")
async def _schema(request) -> AsyncIterator[None]:
    # Nothing selected touches Postgres (e.g. `pytest -m nodb`), so do not
    # connect. Decided over the whole selected set rather than per test because
    # this fixture is session-scoped and builds the schema exactly once.
    if all(item.get_closest_marker("nodb") for item in request.session.items):
        yield
        return

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # `create_all` doesn't carry raw-SQL triggers; install the append-only
        # guard so tests exercise the same immutability as the migrated schema.
        for statement in install_statements(ALL_APPEND_ONLY_TABLES):
            await conn.execute(text(statement))
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean(request, _schema: None) -> AsyncIterator[None]:
    """Reset user-owned tables and reseed feature flags before each test.

    A test marked `@pytest.mark.nodb` skips the truncate, so pure-function
    suites (scoring maths, ranking direction) need no live Postgres. `_schema`
    stays an ordinary parameter: resolving an async fixture imperatively with
    `request.getfixturevalue` makes pytest-asyncio call `Runner.run()` inside
    the already-running loop, which errors the setup of every database test in
    the suite. `_schema` decides for itself whether to connect.
    """
    if request.node.get_closest_marker("nodb"):
        yield
        return
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # CASCADE from users clears wallets/limits/ledger_entries/linked_accounts/
        # metric_models; platform_ledger and raw_payloads have no user FK, so name
        # them explicitly.
        # `users` CASCADE clears everything with a user FK; solo_pools /
        # tournaments have no user FK (their entries do), so name them explicitly.
        await session.execute(
            text(
                "TRUNCATE admin_audit, platform_ledger, raw_payloads, "
                "solo_pools, tournaments, users RESTART IDENTITY CASCADE"
            )
        )
        await session.execute(text("DELETE FROM feature_flags"))
        for key, enabled in DEFAULT_FLAGS.items():
            await session.execute(
                text(
                    "INSERT INTO feature_flags (key, enabled, payload) "
                    "VALUES (:k, :e, '{}'::jsonb)"
                ),
                {"k": key, "e": enabled},
            )
        await session.commit()
    yield


@pytest.fixture(scope="session")
def app():
    return create_app(get_settings())


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A committing session for exercising services directly (no HTTP layer)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as s:
        yield s
        await s.commit()


def new_sessionmaker():
    """Fresh sessionmaker for tests that need independent transactions/connections
    (e.g. the FOR UPDATE concurrency harness)."""
    return get_sessionmaker()


def auth_headers(sub: str, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub, **kwargs)}"}
