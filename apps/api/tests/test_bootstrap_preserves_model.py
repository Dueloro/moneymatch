"""`bootstrap()` must not destroy a model it has no evidence to replace. An empty
result set (host outage, rate limit, no stored games) is not evidence, and
evidence is the only thing allowed to overwrite a model.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.constants import GAME_CHESS_LICHESS
from moneymatch_api.models.skill import MetricModel
from moneymatch_api.services import metric_models_service

from .factories import chess_profile, create_linked_account, create_user

METRIC = "chess_moves"
HOST = "bootstrap_host"


class _FakeAdapter:
    def __init__(self, moves: list[float]):
        self._games = [
            NormGame(
                id=str(i),
                speed="blitz",
                rated=True,
                created_at_ms=1_700_000_000_000 + i * 1000,
                moves=int(v),
                won=True,
                drawn=False,
                metrics={METRIC: v},
            )
            for i, v in enumerate(moves)
        ]

    async def poll_eligible_games(self, _host_account_id, _since_ms, _filters):
        return list(self._games)


async def _linked_user(session, username: str):
    user = await create_user(session, username=username)
    await create_linked_account(
        session,
        user,
        GAME_CHESS_LICHESS,
        host_account_id=HOST,
        profile=chess_profile(HOST),
    )
    return user


async def _model(session, user):
    return await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user.id,
            MetricModel.game == GAME_CHESS_LICHESS,
            MetricModel.metric == METRIC,
        )
    )


async def test_real_history_writes_the_model(session, monkeypatch):
    user = await _linked_user(session, "history_wins")
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([30.0] * 40))
    await metric_models_service.bootstrap(session, user.id, GAME_CHESS_LICHESS, HOST)

    after = await _model(session, user)
    assert after.n == 40
    assert after.mu == pytest.approx(30.0, abs=0.01)


async def test_a_host_outage_does_not_erase_established_history(session, monkeypatch):
    user = await _linked_user(session, "outage_victim")
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([32.0] * 50))
    await metric_models_service.bootstrap(session, user.id, GAME_CHESS_LICHESS, HOST)
    established = await _model(session, user)
    assert established.n == 50

    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([]))
    await metric_models_service.bootstrap(session, user.id, GAME_CHESS_LICHESS, HOST)

    after = await _model(session, user)
    assert after.n == 50, "an outage must not wipe a real baseline"
    assert after.mu == pytest.approx(established.mu)
    assert after.sigma == pytest.approx(established.sigma)


async def test_first_bootstrap_with_no_history_still_creates_a_model(
    session, monkeypatch
):
    user = await _linked_user(session, "brand_new")
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([]))
    await metric_models_service.bootstrap(session, user.id, GAME_CHESS_LICHESS, HOST)

    model = await _model(session, user)
    assert model is not None and model.n == 0
