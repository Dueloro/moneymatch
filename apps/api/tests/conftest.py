"""Pytest fixtures: settings, a real Postgres schema, ASGI client, and JWT minting.

Tests run against a real Postgres (the models use citext/jsonb), pointed at
`TEST_DATABASE_URL` (or a local default). Schema is created once per session;
`users`/`admin_audit` are truncated between tests for isolation.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
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
from moneymatch_api.db.session import get_engine, get_sessionmaker  # noqa: E402
from moneymatch_api.main import create_app  # noqa: E402


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


#: Feature-flag rows exactly as the migration chain seeds them, captured once
#: after `_schema` migrates and replayed by `_clean` before each test.
_SEEDED_FLAGS: list[tuple[str, bool, str]] = []

#: Repo path to `alembic.ini` (tests/ -> apps/api/).
_ALEMBIC_INI = pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_upgrade_head() -> None:
    """Run the migration chain against the test database.

    Synchronous, so it is called via `asyncio.to_thread` — alembic's env.py
    drives its own event loop and cannot be nested inside the running one.
    It reads `DATABASE_URL`, which this module points at the test database
    before any app module is imported.

    **Built without handing alembic the ini file**, deliberately. `migrations/
    env.py` calls `fileConfig(config.config_file_name)` when one is set, and
    `fileConfig` defaults to `disable_existing_loggers=True` — so running
    migrations in-process silently switches off every logger configured before
    it, including `httpx` and `httpcore`. That broke `test_secret_logging.py`,
    which asserts those loggers can still report trouble. Passing no ini leaves
    `config_file_name` as None, env.py skips the logging setup, and only
    `script_location` is needed because env.py sets the database URL itself.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "migrations"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def _schema(request) -> AsyncIterator[None]:
    # Nothing selected touches Postgres (e.g. `pytest -m nodb`), so do not
    # connect. Decided over the whole selected set rather than per test because
    # this fixture is session-scoped and builds the schema exactly once.
    if all(item.get_closest_marker("nodb") for item in request.session.items):
        yield
        return

    engine = get_engine()
    # Build the test schema by running the **migration chain**, not `create_all`.
    #
    # `create_all` carries no migration seed data, no raw-SQL triggers and no
    # guarantee of agreeing with the chain. That gap is what let the geo-fence
    # bug reach production: the fence reads its state list from a row seeded by
    # migration 0001, that row never existed in tests, and the fence therefore
    # read "unconfigured" in every test that has ever run. See
    # AUDIT_FINDINGS.md P0-1.
    #
    # Running migrations costs ~3 seconds once per session against a ~11.5
    # minute suite, and it continuously proves the thing every deploy relies on:
    # that the chain applies cleanly to an empty database.
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await asyncio.to_thread(_alembic_upgrade_head)

    # Capture the seeded state so `_clean` can restore exactly what the
    # migrations produced, rather than holding its own opinion about what
    # should exist — an opinion is the thing that drifts.
    global _SEEDED_FLAGS
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await session.execute(
            text("SELECT key, enabled, payload FROM feature_flags")
        )
        _SEEDED_FLAGS = [(r.key, r.enabled, json.dumps(r.payload or {})) for r in rows]

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
        # Restore feature flags to exactly what the migration chain seeded.
        #
        # Deliberately not rebuilt from `DEFAULT_FLAGS`: that is a code-side
        # opinion about what flags exist, and it disagreed with the migrations in
        # four places — it was missing `geo_config` (with its 14-state payload),
        # `worker_heartbeat` and `game:cs2.faceit`, and it invented
        # `game:cs2.steam`, which no migration seeds (AUDIT_FINDINGS.md P1-1).
        # Replaying the captured rows means the fixture can no longer drift.
        #
        # Tests needing a different geo list override it (see `test_geo_service`);
        # the default test user is in MA, which is not excluded.
        await session.execute(text("DELETE FROM feature_flags"))
        for key, enabled, payload in _SEEDED_FLAGS:
            await session.execute(
                text(
                    "INSERT INTO feature_flags (key, enabled, payload) "
                    "VALUES (:k, :e, cast(:p as jsonb))"
                ),
                {"k": key, "e": enabled, "p": payload},
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
