"""Server-side analytics seam (09-phase-6 · deliverable 3).

Unconfigured ⇒ a safe no-op (tests never hit the network). The money/liquidity
events fire from the settlement path — asserted by monkeypatching `capture`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from moneymatch_api.adapters import registry
from moneymatch_api.services import analytics

from .test_settlement_worker import FakeCS2Adapter, _game, setup_active_cs2

pytestmark = pytest.mark.asyncio


async def test_capture_is_noop_without_key():
    analytics.reset_for_tests()
    # No POSTHOG_API_KEY in the test env → returns cleanly, no exception, no network.
    analytics.capture("entry_queued", "user-123", {"x": 1})
    assert analytics._ensure_client() is False


async def test_settlement_emits_money_events(monkeypatch):
    from .conftest import new_sessionmaker

    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        analytics,
        "capture",
        lambda event, distinct_id, properties=None: events.append(
            (event, str(distinct_id))
        ),
    )

    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    from moneymatch_api.workers import settlement_worker

    await settlement_worker.run_cycle(sm, now=info["matched_at"] + timedelta(seconds=5))

    names = {e for e, _ in events}
    assert analytics.CONTEST_SETTLED in names
    assert analytics.RAKE_COLLECTED in names


async def test_capture_routes_to_posthog_when_enabled(monkeypatch):
    """With the client forced live, capture forwards to the posthog module."""
    import sys
    import types

    recorded: list[dict] = []
    fake_posthog = types.ModuleType("posthog")
    fake_posthog.api_key = None
    fake_posthog.host = None
    fake_posthog.capture = lambda event, distinct_id=None, properties=None: (
        recorded.append(
            {"event": event, "distinct_id": distinct_id, "properties": properties}
        )
    )
    monkeypatch.setitem(sys.modules, "posthog", fake_posthog)
    monkeypatch.setattr(analytics, "_initialized", True)
    monkeypatch.setattr(analytics, "_enabled", True)

    analytics.capture("match_found", "user-9", {"game": "cs2.faceit"})
    assert recorded == [
        {
            "event": "match_found",
            "distinct_id": "user-9",
            "properties": {"game": "cs2.faceit"},
        }
    ]
