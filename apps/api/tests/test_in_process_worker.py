"""In-process settlement worker (RUN_WORKER_IN_PROCESS) — the free-tier option
where one web service runs both the API and the settlement loop. The loop starts
on lifespan startup and is cancelled cleanly on shutdown."""

from __future__ import annotations

import asyncio

import pytest

from moneymatch_api.config import Settings
from moneymatch_api.main import create_app, lifespan

from .conftest import TEST_DB_URL, TEST_JWT_SECRET

pytestmark = pytest.mark.asyncio


def _settings(**overrides) -> Settings:
    base = dict(
        env="local",
        database_url=TEST_DB_URL,
        supabase_url="https://test-project.supabase.co",
        supabase_jwt_secret=TEST_JWT_SECRET,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _keep_shared_engine(monkeypatch):
    # The real lifespan disposes the global engine on shutdown; no-op it so this
    # test doesn't tear down the engine the rest of the session shares.
    async def _noop() -> None:
        return None

    monkeypatch.setattr("moneymatch_api.main.dispose_engine", _noop)


async def test_worker_runs_in_process_when_enabled(monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_run_forever(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(
        "moneymatch_api.workers.settlement_worker.run_forever", fake_run_forever
    )

    app = create_app(_settings(run_worker_in_process=True))
    async with lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)
    # Exiting the lifespan cancels the background task cleanly (no hang).
    assert cancelled.is_set()


async def test_worker_not_started_when_disabled(monkeypatch):
    started = asyncio.Event()

    async def fake_run_forever(*args, **kwargs):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(
        "moneymatch_api.workers.settlement_worker.run_forever", fake_run_forever
    )

    app = create_app(_settings(run_worker_in_process=False))
    async with lifespan(app):
        await asyncio.sleep(0.05)
    assert not started.is_set()
