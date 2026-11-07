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

# No module-level `pytest.mark.asyncio`: `asyncio_mode = "auto"` in pyproject
# already collects every async test here, so the marker was redundant — and
# applying it to the three pure z-test functions below made pytest warn on each
# one. Warnings in a money-relevant control are where a real warning goes to
# hide (AUDIT_FINDINGS.md P2-1).

CHESS = "chess.lichess"
METRIC = "chess_moves"


@pytest.mark.nodb
def test_sandbag_z_none_without_enough_history():
    assert sandbagging_service.sandbag_z([1.0] * 8) is None


@pytest.mark.nodb
def test_sandbag_z_flags_a_tanked_recent_window():
    # Older baseline steady ~1.5; recent 10 tanked to ~0.6 → strongly negative z.
    baseline = [1.5, 1.4, 1.6, 1.5, 1.5, 1.4, 1.6]
    recent = [0.6] * 10
    z = sandbagging_service.sandbag_z(recent + baseline, recent_n=10)
    assert z is not None and z < -1.5


@pytest.mark.nodb
def test_sandbag_z_steady_form_not_flagged():
    values = [1.5, 1.4, 1.6, 1.5, 1.55, 1.45] * 4
    z = sandbagging_service.sandbag_z(values, recent_n=10)
    assert z is None or z >= -1.5


class _FakeAdapter:
    def __init__(self, values_oldest_first):
        # NormGame list is oldest-first (as adapters return).
        self._games = [
            NormGame(
                id=str(i),
                speed="blitz",
                rated=True,
                created_at_ms=i,
                moves=0,
                won=None,
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
    # Oldest-first: steady baseline then a tanked recent tail.
    baseline = [1.5, 1.4, 1.6, 1.5, 1.5, 1.4, 1.6]
    recent_tanked = [0.6] * 10
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

    # Adapter would raise if called — the existing flag short-circuits first.
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
    steady = [1.5, 1.4, 1.6, 1.5, 1.55, 1.45] * 4
    monkeypatch.setattr(registry, "get", lambda g: _FakeAdapter(steady))
    # No raise.
    await sandbagging_service.assert_not_sandbagging(
        session, user, CHESS, METRIC, "host_clean"
    )
