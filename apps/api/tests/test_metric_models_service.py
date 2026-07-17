"""Metric-model bootstrap: EWMA math, provisional/history floors, and upsert."""

from __future__ import annotations

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


async def test_bootstrap_noop_for_win_only_game(session, monkeypatch):
    user = await create_user(session)
    called = False

    def _get(gid):
        nonlocal called
        called = True
        return _FakeCS2Adapter([])

    monkeypatch.setattr(registry, "get", _get)
    assert await svc.bootstrap(session, user.id, "chess.lichess", "magnus") == []
    assert called is False  # no rate metrics → adapter never polled
