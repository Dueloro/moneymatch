"""With demo simulation on, ingestion must still use the real adapter's
budget-aware `fetch_history` (PUBG: only unseen match ids), and add injected
demo matches on top — never fall back to re-downloading the full history."""

from __future__ import annotations

import pytest

from moneymatch_api.adapters.base import GameAdapter, HistoryBatch, NormGame
from moneymatch_api.adapters.simulated import SimulatedGamesAdapter
from moneymatch_api.services import demo_simulation

pytestmark = [pytest.mark.asyncio, pytest.mark.nodb]


def _g(gid: str, ms: int) -> NormGame:
    return NormGame(
        id=gid,
        speed="squad",
        rated=True,
        created_at_ms=ms,
        moves=0,
        won=False,
        drawn=False,
        metrics={"pubg_kills": 1.0},
    )


class _Inner(GameAdapter):
    id = "pubg.steam"

    def __init__(self):
        self.fetch_calls = 0
        self.poll_calls = 0

    async def link_account(self, method, identifier):  # pragma: no cover
        raise NotImplementedError

    async def fetch_profile(self, account_id):  # pragma: no cover
        raise NotImplementedError

    async def poll_eligible_games(self, account_id, since_ms, filters):
        self.poll_calls += 1
        return []

    async def fetch_history(self, account_id, since_ms, *, known_ids, first_poll):
        self.fetch_calls += 1
        return HistoryBatch([_g("real1", 2000)], complete=False)


async def test_simulated_wrapper_uses_the_real_fetch_and_adds_injected(monkeypatch):
    async def fake_games_for(game, account, since_ms, speed):
        return [_g("sim1", 1000), _g("known", 1500)]

    monkeypatch.setattr(demo_simulation, "games_for", fake_games_for)
    inner = _Inner()
    batch = await SimulatedGamesAdapter(inner).fetch_history(
        "acct", 0, known_ids={"known"}, first_poll=False
    )
    assert inner.fetch_calls == 1 and inner.poll_calls == 0
    assert [g.id for g in batch.games] == ["sim1", "real1"]
    assert batch.complete is False  # the real fetch's verdict is kept
