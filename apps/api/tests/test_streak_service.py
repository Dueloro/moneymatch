"""Phase 4 integration — streak persistence + settlement hook (DB-backed).

Also exercises migration 0032 via the real chain (conftest builds the schema by
running migrations).
"""

from __future__ import annotations

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services import streak_service
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state as bstate
from tests.factories import create_user

CHESS_BLITZ = mk.get("chess.lichess", "blitz", "chess_moves")


def _norm(pid, i, moves):
    return NormGame(
        id=f"{pid}-{i}", speed="blitz", rated=True,
        created_at_ms=1_760_000_000_000 + i, moves=int(moves), won=True,
        drawn=False, metrics={"chess_moves": float(moves)},
    )


async def _apply(session, uid, won):
    return await streak_service.apply_result(
        session, uid, "chess.lichess", "blitz", won
    )


async def test_apply_result_climbs_and_resets(session):
    u = await create_user(session)
    # Three wins climb; a loss resets; a draw holds.
    assert (await _apply(session, u.id, True)).streak == 1
    assert (await _apply(session, u.id, True)).streak == 2
    row = await _apply(session, u.id, True)
    assert row.streak == 3 and row.best_streak == 3
    lost = await _apply(session, u.id, False)
    assert lost.streak == 0 and lost.best_streak == 3  # best remembered
    drew = await _apply(session, u.id, None)
    assert drew.streak == 0


async def test_get_streak_defaults_to_zero(session):
    u = await create_user(session)
    assert await streak_service.get_streak(session, u.id, "chess.lichess", "blitz") == 0


async def test_matchmaking_target_none_when_unplaced(session):
    u = await create_user(session)
    target = await streak_service.matchmaking_target_for(session, u.id, CHESS_BLITZ)
    assert target is None


async def test_matchmaking_target_climbs_with_streak(session):
    u = await create_user(session)
    # Place the player (index + bucket) with an active reference.
    ref = rf.build_reference(
        [float(v) for v in range(20, 60)], 3, lower_is_better=True
    )
    await bstate.activate_reference(
        session, ref, "chess.lichess", "blitz", "chess_moves", version=1
    )
    for i in range(6):
        await bstate.record_and_update(
            session, u.id, "chess.lichess", _norm(u.id, i, 30)
        )

    base = await streak_service.matchmaking_target_for(session, u.id, CHESS_BLITZ)
    assert base is not None

    # A win streak shifts the target (chess = lower-is-better → target moves DOWN,
    # i.e. toward stronger opponents).
    for _ in range(3):
        await _apply(session, u.id, True)
    climbed = await streak_service.matchmaking_target_for(session, u.id, CHESS_BLITZ)
    assert climbed < base
