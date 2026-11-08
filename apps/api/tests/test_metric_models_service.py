"""Metric-model bootstrap: EWMA math and upsert."""

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
        speed="blitz",
        rated=True,
        created_at_ms=int(match_id),
        moves=0,
        won=True,
        drawn=False,
        metrics=metrics,
    )


def test_compute_ewma_empty_and_single():
    assert svc.compute_ewma([]) == (0.0, 0.0, 0)
    mu, sigma, n = svc.compute_ewma([1.5])
    assert mu == 1.5 and sigma == 0.0 and n == 1


def test_compute_ewma_weights_recent_samples_more():
    mu, sigma, n = svc.compute_ewma([1.0, 1.0, 1.0, 10.0], half_life=2)
    assert n == 4
    assert mu > 3.25
    assert sigma > 0


class _FakeAdapter:
    def __init__(self, games):
        self._games = games

    async def poll_eligible_games(self, account_id, since_ms, filters: GameFilters):
        return self._games


async def test_bootstrap_writes_metric_models(session, monkeypatch):
    user = await create_user(session)
    games = [_norm("1", chess_moves=30.0), _norm("2", chess_moves=40.0)]
    monkeypatch.setattr(registry, "get", lambda gid: _FakeAdapter(games))

    written = await svc.bootstrap(session, user.id, "chess.lichess", "magnus")
    assert {m.metric for m in written} == {"chess_moves"}
    assert all(m.n == 2 for m in written)

    rows = list(
        await session.scalars(select(MetricModel).where(MetricModel.user_id == user.id))
    )
    assert len(rows) == 1


async def test_bootstrap_is_idempotent_upsert(session, monkeypatch):
    user = await create_user(session)
    monkeypatch.setattr(
        registry, "get", lambda gid: _FakeAdapter([_norm("1", chess_moves=30.0)])
    )
    await svc.bootstrap(session, user.id, "chess.lichess", "magnus")
    await svc.bootstrap(session, user.id, "chess.lichess", "magnus")

    rows = list(
        await session.scalars(
            select(MetricModel).where(
                MetricModel.user_id == user.id, MetricModel.metric == "chess_moves"
            )
        )
    )
    assert len(rows) == 1


async def test_bootstrap_noop_for_a_game_with_no_rate_metrics(session, monkeypatch):
    user = await create_user(session)
    called = False

    def _get(gid):
        nonlocal called
        called = True
        return _FakeAdapter([])

    monkeypatch.setattr(registry, "get", _get)
    monkeypatch.setitem(svc.GAME_RATE_METRICS, "chess.lichess", ())

    assert await svc.bootstrap(session, user.id, "chess.lichess", "magnus") == []
    assert called is False
