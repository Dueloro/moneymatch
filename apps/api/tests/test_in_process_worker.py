"""In-process settlement worker (RUN_WORKER_IN_PROCESS) — the free-tier option
where one web service runs both the API and the settlement loop. The loop starts
on lifespan startup and is cancelled cleanly on shutdown."""

from __future__ import annotations

import asyncio
import contextlib

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


async def test_the_worker_runs_in_the_api_process_by_default(monkeypatch):
    """One process runs everything unless explicitly turned off (free tiers)."""
    monkeypatch.delenv("RUN_WORKER_IN_PROCESS", raising=False)
    assert _settings().run_worker_in_process is True


async def test_only_one_worker_loop_holds_the_lock():
    """Two processes (or two loops) starting the worker: one works, one waits,
    and the waiting one takes over when the first lets go."""
    from moneymatch_api.workers.settlement_worker import WorkerLock

    # A key of its own so this test never collides with a real worker.
    first, second = WorkerLock(key=987_654_321), WorkerLock(key=987_654_321)
    try:
        assert await first.acquire() is True
        assert await first.acquire() is True  # re-checking keeps it
        assert await second.acquire() is False  # standby
        await first.release()
        assert await second.acquire() is True  # takeover
    finally:
        await first.release()
        await second.release()


async def test_a_standby_loop_does_no_work(monkeypatch):
    """While another process holds the lock, run_forever never runs a cycle."""
    from moneymatch_api.workers import settlement_worker
    from moneymatch_api.workers.settlement_worker import WORKER_LOCK_KEY, WorkerLock

    holder = WorkerLock(key=WORKER_LOCK_KEY)
    cycles = 0

    async def counting_pass(sm):
        nonlocal cycles
        cycles += 1

    monkeypatch.setattr(settlement_worker, "_one_pass", counting_pass)
    try:
        assert await holder.acquire()
        task = asyncio.create_task(settlement_worker.run_forever(interval=0))
        await asyncio.sleep(0.3)
        assert cycles == 0  # standing by
        await holder.release()
        for _ in range(50):
            if cycles:
                break
            await asyncio.sleep(0.05)
        assert cycles > 0  # took over once the lock was free
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        await holder.release()
