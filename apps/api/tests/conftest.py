"""Pytest fixtures: settings, a real Postgres schema, ASGI client, and JWT minting."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time
import uuid
from collections.abc import AsyncIterator

import jwt
import pytest
import pytest_asyncio

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
os.environ["RATE_LIMIT_WRITES_PER_MINUTE"] = "100000"

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


# : Feature-flag rows exactly as the migration chain seeds them, captured once : after
# `_schema` migrates and replayed by `_clean` before each test.
_SEEDED_FLAGS: list[tuple[str, bool, str]] = []

_ALEMBIC_INI = pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_upgrade_head() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "migrations"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def _schema(request) -> AsyncIterator[None]:
    # Decided over the whole selected set rather than per test because this fixture is
    # session-scoped and builds the schema exactly once.
    if all(item.get_closest_marker("nodb") for item in request.session.items):
        yield
        return

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await asyncio.to_thread(_alembic_upgrade_head)

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
    if request.node.get_closest_marker("nodb"):
        yield
        return
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # CASCADE from users clears wallets/limits/ledger_entries/linked_accounts/
        # metric_models; platform_ledger and raw_payloads have no user FK, so name them
        # explicitly.
        await session.execute(
            text(
                "TRUNCATE admin_audit, platform_ledger, raw_payloads, "
                "solo_pools, tournaments, users RESTART IDENTITY CASCADE"
            )
        )
        # Tests needing a different geo list override it (see `test_geo_service`); the
        # default test user is in MA, which is not excluded.
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


@pytest.fixture(autouse=True)
def _lichess_broker(monkeypatch) -> None:
    from moneymatch_api.services.hosts import lichess

    async def _open_challenge(clock_limit, clock_increment=0, *, users=None):
        game_id = uuid.uuid4().hex[:8]
        return {
            "game_id": game_id,
            "urls": {
                "white": f"https://lichess.org/{game_id}?color=white",
                "black": f"https://lichess.org/{game_id}?color=black",
            },
        }

    monkeypatch.setattr(lichess, "create_open_challenge", _open_challenge)


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
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as s:
        yield s
        await s.commit()


def new_sessionmaker():
    return get_sessionmaker()


def auth_headers(sub: str, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub, **kwargs)}"}
