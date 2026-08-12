"""Metric-model bootstrap: EWMA math, provisional/history floors, and upsert."""

from __future__ import annotations

import httpx
import respx
from sqlalchemy import select

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import GameFilters, NormGame
from moneymatch_api.models.skill import MetricModel
from moneymatch_api.services import metric_models_service as svc

from .factories import create_user


def _norm(match_id, **metrics):
    return NormGame(
        id=match_id,
        speed="cs2",
        rated=True,
        created_at_ms=int(match_id),
        moves=0,
        won=True,
        drawn=False,
        metrics=metrics,
    )


# --------------------------------------------------------------------------- #
# Pure EWMA math
# --------------------------------------------------------------------------- #


def test_compute_ewma_empty_and_single():
    assert svc.compute_ewma([]) == (0.0, 0.0, 0)
    mu, sigma, n = svc.compute_ewma([1.5])
    assert mu == 1.5 and sigma == 0.0 and n == 1


def test_compute_ewma_weights_recent_samples_more():
    # Oldest-first: three lows then a recent high. Recency weighting pulls the
    # mean above the simple average (3.25).
    mu, sigma, n = svc.compute_ewma([1.0, 1.0, 1.0, 10.0], half_life=2)
    assert n == 4
    assert mu > 3.25
    assert sigma > 0


def test_provisional_and_history_floors():
    assert svc.is_provisional(MetricModel(n=9)) is True
    assert svc.is_provisional(MetricModel(n=10)) is False
    assert svc.meets_history_floor("cs2.faceit", 25) is True
    assert svc.meets_history_floor("cs2.faceit", 24) is False
    assert svc.meets_history_floor("chess.lichess", 20) is True


# --------------------------------------------------------------------------- #
# Bootstrap against a fake adapter
# --------------------------------------------------------------------------- #


class _FakeCS2Adapter:
    def __init__(self, games):
        self._games = games

    async def poll_eligible_games(self, account_id, since_ms, filters: GameFilters):
        return self._games


async def test_bootstrap_writes_metric_models(session, monkeypatch):
    user = await create_user(session)
    games = [
        _norm("1", cs2_kd_ratio=1.0, cs2_adr=70.0, cs2_headshot_pct=40.0),
        _norm("2", cs2_kd_ratio=1.4, cs2_adr=90.0, cs2_headshot_pct=50.0),
    ]
    monkeypatch.setattr(registry, "get", lambda gid: _FakeCS2Adapter(games))

    written = await svc.bootstrap(session, user.id, "cs2.faceit", "s1mple")
    assert {m.metric for m in written} == {
        "cs2_kd_ratio",
        "cs2_adr",
        "cs2_headshot_pct",
    }
    assert all(m.n == 2 for m in written)

    rows = list(
        await session.scalars(select(MetricModel).where(MetricModel.user_id == user.id))
    )
    assert len(rows) == 3


async def test_bootstrap_is_idempotent_upsert(session, monkeypatch):
    user = await create_user(session)
    monkeypatch.setattr(
        registry, "get", lambda gid: _FakeCS2Adapter([_norm("1", cs2_adr=80.0)])
    )
    await svc.bootstrap(session, user.id, "cs2.faceit", "s1mple")
    await svc.bootstrap(session, user.id, "cs2.faceit", "s1mple")  # re-run

    rows = list(
        await session.scalars(
            select(MetricModel).where(
                MetricModel.user_id == user.id, MetricModel.metric == "cs2_adr"
            )
        )
    )
    assert len(rows) == 1  # upserted, not duplicated


async def test_bootstrap_noop_for_a_game_with_no_rate_metrics(session, monkeypatch):
    """A game the registry has no per-match metric for never reaches its host.

    Chess used to be the example here. It now carries `chess_moves`, so it
    bootstraps like any other game; this pins the general rule instead.
    """
    user = await create_user(session)
    called = False

    def _get(gid):
        nonlocal called
        called = True
        return _FakeCS2Adapter([])

    monkeypatch.setattr(registry, "get", _get)
    monkeypatch.setitem(svc.GAME_RATE_METRICS, "chess.lichess", ())

    assert await svc.bootstrap(session, user.id, "chess.lichess", "magnus") == []
    assert called is False  # no rate metrics → adapter never polled


# --------------------------------------------------------------------------- #
# Worker sweep — deferred (PUBG) accounts bootstrapped out-of-band
# --------------------------------------------------------------------------- #


@respx.mock
async def test_worker_bootstraps_pending_pubg_link(session, monkeypatch):
    from sqlalchemy import select as _select

    from moneymatch_api.config import get_settings
    from moneymatch_api.db.session import get_sessionmaker
    from moneymatch_api.models.linked_account import LinkedAccount
    from moneymatch_api.models.skill import MetricModel
    from moneymatch_api.services.hosts import pubg
    from moneymatch_api.workers import settlement_worker

    sm = get_sessionmaker()

    monkeypatch.setattr(get_settings(), "pubg_api_key", "test-key")
    pubg.clear_match_cache()
    user = await create_user(session)
    account = "account.pending"
    link = LinkedAccount(
        user_id=user.id,
        game="pubg.steam",
        host_account_id=account,
        host_username="pending",
        models_bootstrapped_at=None,  # bootstrap owed
    )
    session.add(link)
    await session.commit()

    shard = "https://api.pubg.com/shards/steam"
    match_ids = [f"m{i}" for i in range(12)]
    respx.get(f"{shard}/players/{account}").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": account,
                    "attributes": {"name": "pending"},
                    "relationships": {
                        "matches": {
                            "data": [{"type": "match", "id": m} for m in match_ids]
                        }
                    },
                }
            },
        )
    )
    for i, m in enumerate(match_ids):
        respx.get(f"{shard}/matches/{m}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": m,
                        "attributes": {
                            "gameMode": "squad-fpp",
                            "matchType": "official",
                            "isCustomMatch": False,
                            "createdAt": f"2026-07-{i + 1:02d}T00:00:00Z",
                        },
                    },
                    "included": [
                        {
                            "type": "participant",
                            "attributes": {
                                "stats": {
                                    "playerId": account,
                                    "kills": 4 + i,
                                    "headshotKills": 1,
                                    "damageDealt": 300.0 + i,
                                    "winPlace": 1 if i % 2 else 5,
                                }
                            },
                        }
                    ],
                },
            )
        )

    count = await settlement_worker._bootstrap_pending_models(sm)
    assert count == 1

    n = await session.scalar(
        _select(MetricModel.n).where(
            MetricModel.user_id == user.id,
            MetricModel.game == "pubg.steam",
            MetricModel.metric == "pubg_kills",
        )
    )
    assert n is not None and n >= 10  # Issue 1: stat duels no longer provisional
    refreshed = await session.get(LinkedAccount, link.id)
    await session.refresh(refreshed)
    assert refreshed.models_bootstrapped_at is not None  # stamped once
