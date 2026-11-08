"""Sentry init is shared by the API and the worker."""

from __future__ import annotations

import pytest
import sentry_sdk

from moneymatch_api import config, observability
from moneymatch_api.config import Settings
from moneymatch_api.workers import settlement_worker

pytestmark = pytest.mark.nodb


def _settings(**overrides: str) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://u:p@h/db",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def test_no_dsn_is_a_noop(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    observability.init_sentry(_settings(sentry_dsn=""))
    assert calls == []


def test_dsn_initialises_with_render_commit(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    observability.init_sentry(_settings(sentry_dsn="https://k@o.ingest.sentry.io/1"))
    assert calls[0]["dsn"] == "https://k@o.ingest.sentry.io/1"
    assert calls[0]["release"] == "abc123"


def test_worker_main_initialises_sentry(monkeypatch):
    settings = _settings(sentry_dsn="https://k@o.ingest.sentry.io/1")
    seen: list[Settings] = []
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(observability, "init_sentry", seen.append)

    async def _no_loop() -> None:
        return None

    monkeypatch.setattr(settlement_worker, "run_forever", _no_loop)
    settlement_worker.main()
    assert seen == [settings]
