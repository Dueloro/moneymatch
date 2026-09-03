"""Wiring test gate — the bucketing nightly pass (DB-backed)."""

from __future__ import annotations

from sqlalchemy import func, select

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.models.bucketing import AuditEvent
from moneymatch_api.services.bucketing import state as state_svc
from moneymatch_api.workers import bucketing_nightly as bn
from tests.conftest import new_sessionmaker
from tests.factories import create_user


def _norm(pid, i, moves):
    return NormGame(
        id=f"{pid}-{i}", speed="blitz", rated=True,
        created_at_ms=1_760_000_000_000 + i, moves=int(moves), won=True,
        drawn=False, metrics={"chess_moves": float(moves)},
    )


async def _play(session, moves):
    u = await create_user(session)
    for i, m in enumerate(moves):
        await state_svc.record_and_update(
            session, u.id, "chess.lichess", _norm(u.id, i, m)
        )
    return u


async def test_nightly_bootstraps_a_reference_once_enough_players(session):
    # 25 placed chess-blitz players, no reference yet → nightly creates version 1.
    for k in range(25):
        await _play(session, [20 + (k % 30)] * 5)
    await session.commit()

    sm = new_sessionmaker()
    report = await bn.run_bucketing_nightly(sm)
    assert report.references_created >= 1

    ref = await state_svc.get_active_reference(
        session, "chess.lichess", "blitz", "chess_moves"
    )
    assert ref is not None
    assert ref.version == 1
    assert ref.source == "ours"

    # The players already ingested (bucket was None) are now placed — so they can
    # wager immediately, not only after their next match.
    from moneymatch_api.models.bucketing import MarketState

    states = list(
        await session.scalars(
            select(MarketState).where(MarketState.game == "chess.lichess")
        )
    )
    assert states and all(s.bucket is not None for s in states)
    assert all(s.bucket_version == 1 for s in states)


async def test_nightly_records_promotion_advice(session):
    for k in range(25):
        await _play(session, [20 + (k % 30)] * 8)
    await session.commit()
    sm = new_sessionmaker()
    # First pass creates the reference; second produces advice against it.
    await bn.run_bucketing_nightly(sm)
    await bn.run_bucketing_nightly(sm)
    n = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.event_type == "promotion_advice")
    )
    assert n >= 1


async def test_nightly_is_safe_on_an_empty_market(session):
    sm = new_sessionmaker()
    report = await bn.run_bucketing_nightly(sm)  # no players at all
    assert report.references_created == 0
    assert report.promotion_advices == 0
