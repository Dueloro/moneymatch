"""Sandbagging detector v1: the pure z-test and the flag-and-block evaluation."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.models.risk import RiskFlag
from moneymatch_api.services import sandbagging_service
from moneymatch_api.services.sandbagging_service import SandbaggingBlockedError

from .factories import chess_profile, create_linked_account, create_user

CHESS = "chess.lichess"
METRIC = "chess_moves"


@pytest.mark.nodb
def test_sandbag_z_none_without_enough_history():
    assert sandbagging_service.sandbag_z([1.0] * 8) is None


@pytest.mark.nodb
def test_sandbag_z_flags_a_tanked_recent_window():
    baseline = [1.5, 1.4, 1.6, 1.5, 1.5, 1.4, 1.6]
    recent = [0.6] * 10
    z = sandbagging_service.sandbag_z(recent + baseline, recent_n=10)
    assert z is not None and z < -1.5


@pytest.mark.nodb
def test_sandbag_z_flips_for_lower_is_better():
    baseline = [34.0, 36.0, 35.0, 33.0, 37.0, 35.0, 34.0]
    slower = [55.0] * 10
    faster = [20.0] * 10
    z_slow = sandbagging_service.sandbag_z(
        slower + baseline, recent_n=10, lower_is_better=True
    )
    z_fast = sandbagging_service.sandbag_z(
        faster + baseline, recent_n=10, lower_is_better=True
    )
    assert z_slow is not None and z_slow < -1.5
    assert z_fast is not None and z_fast > 0


@pytest.mark.nodb
def test_sandbag_z_steady_form_not_flagged():
    values = [1.5, 1.4, 1.6, 1.5, 1.55, 1.45] * 4
    z = sandbagging_service.sandbag_z(values, recent_n=10)
    assert z is None or z >= -1.5


class _FakeAdapter:
    def __init__(self, values_oldest_first):
        self._games = [
            NormGame(
                id=str(i),
                speed="blitz",
                rated=True,
                created_at_ms=i,
                moves=int(v),
                won=True,
                drawn=False,
                metrics={METRIC: v},
            )
            for i, v in enumerate(values_oldest_first)
        ]

    async def poll_eligible_games(self, host, since_ms, filters):
        return self._games


async def test_evaluate_writes_flag_and_blocks(session, monkeypatch):
    user = await create_user(session, username="tank")
    await create_linked_account(
        session, user, CHESS, host_account_id="host_tank", profile=chess_profile("tank")
    )
    baseline = [34.0, 36.0, 35.0, 33.0, 37.0, 35.0, 34.0]
    recent_tanked = [55.0, 54.0, 56.0, 55.0, 53.0, 57.0, 55.0, 54.0, 56.0, 55.0]
    monkeypatch.setattr(
        registry, "get", lambda g: _FakeAdapter(baseline + recent_tanked)
    )

    with pytest.raises(SandbaggingBlockedError):
        await sandbagging_service.assert_not_sandbagging(
            session, user, CHESS, METRIC, "host_tank"
        )
    flag = await session.scalar(select(RiskFlag).where(RiskFlag.user_id == user.id))
    assert flag is not None and flag.kind == "sandbagging" and flag.resolved is False


async def test_existing_flag_blocks_without_re_evaluating(session, monkeypatch):
    user = await create_user(session, username="flagged")
    session.add(
        RiskFlag(user_id=user.id, game=CHESS, metric=METRIC, kind="sandbagging")
    )
    await session.flush()

    def _boom(_g):
        raise AssertionError("should not evaluate when already flagged")

    monkeypatch.setattr(registry, "get", _boom)
    with pytest.raises(SandbaggingBlockedError):
        await sandbagging_service.assert_not_sandbagging(
            session, user, CHESS, METRIC, "host_flagged"
        )


async def test_steady_player_not_blocked(session, monkeypatch):
    user = await create_user(session, username="clean")
    await create_linked_account(
        session,
        user,
        CHESS,
        host_account_id="host_clean",
        profile=chess_profile("clean"),
    )
    steady = [34.0, 36.0, 35.0, 33.0, 37.0, 35.0] * 4
    monkeypatch.setattr(registry, "get", lambda g: _FakeAdapter(steady))
    await sandbagging_service.assert_not_sandbagging(
        session, user, CHESS, METRIC, "host_clean"
    )


async def test_improving_player_not_blocked(session, monkeypatch):
    user = await create_user(session, username="improver")
    await create_linked_account(
        session,
        user,
        CHESS,
        host_account_id="host_improver",
        profile=chess_profile("improver"),
    )
    baseline = [34.0, 36.0, 35.0, 33.0, 37.0, 35.0, 34.0]
    recent_faster = [20.0, 21.0, 19.0, 20.0, 22.0, 18.0, 20.0, 21.0, 19.0, 20.0]
    monkeypatch.setattr(
        registry, "get", lambda g: _FakeAdapter(baseline + recent_faster)
    )
    await sandbagging_service.assert_not_sandbagging(
        session, user, CHESS, METRIC, "host_improver"
    )
    flag = await session.scalar(select(RiskFlag).where(RiskFlag.user_id == user.id))
    assert flag is None
