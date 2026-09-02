"""Integration test gate — the record→index→bucket pipeline (Phases 1–3, DB).

DB-backed (needs Postgres → CI). Proves the pure engines are wired to
`market_state` / `market_reference` correctly: one match flows through
`record_and_update` into a persisted index and bucket, re-ingest doesn't
double-count, and the active-reference swap keeps exactly one version live.
"""

from __future__ import annotations

import uuid

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state

CHESS_BLITZ = mk.get("chess.lichess", "blitz", "chess_moves")


def _norm(id, moves, created=1_760_000_000_000, won=True):
    return NormGame(
        id=id,
        speed="blitz",
        rated=True,
        created_at_ms=created,
        moves=int(moves),
        won=won,
        drawn=False,
        metrics={"chess_moves": float(moves)},
    )


async def _make_user(session) -> uuid.UUID:
    from moneymatch_api.models.user import User

    u = User(
        auth_id=f"auth-{uuid.uuid4()}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        residence_state="MA",
    )
    session.add(u)
    await session.flush()
    return u.id


async def test_record_and_update_builds_index_and_persists(session):
    player = await _make_user(session)
    for i, moves in enumerate([30, 28, 34, 26, 31]):
        await state.record_and_update(
            session,
            player,
            "chess.lichess",
            _norm(f"g{i}", moves, created=1_760_000_000_000 + i),
        )
    row = await state.get_market_state(
        session, player, "chess.lichess", "blitz", "chess_moves"
    )
    assert row is not None
    assert row.n_samples == 5
    assert 24.0 <= row.index_value <= 34.0  # a low-move (good) index
    assert row.provisional is True  # below the provisional floor still


async def test_reingest_does_not_double_count_the_index(session):
    player = await _make_user(session)
    n = _norm("dup", 30)
    await state.record_and_update(session, player, "chess.lichess", n)
    await state.record_and_update(session, player, "chess.lichess", n)  # re-seen
    row = await state.get_market_state(
        session, player, "chess.lichess", "blitz", "chess_moves"
    )
    assert row.n_samples == 1  # the second call was a no-op


async def test_active_reference_swap_keeps_exactly_one_active(session):
    game, mode, metric = "chess.lichess", "blitz", "chess_moves"
    v1 = rf.build_reference([float(v) for v in range(20, 60)], 3, lower_is_better=True)
    await state.activate_reference(session, v1, game, mode, metric, version=1)
    active1 = await state.get_active_reference(session, game, mode, metric)
    assert active1.version == 1

    v2 = rf.build_reference([float(v) for v in range(20, 80)], 3, lower_is_better=True)
    await state.activate_reference(session, v2, game, mode, metric, version=2)
    active2 = await state.get_active_reference(session, game, mode, metric)
    assert active2.version == 2  # the swap moved active forward

    # And there is exactly one active row (the partial unique index guarantees it).
    from sqlalchemy import func, select

    from moneymatch_api.models.bucketing import MarketReference

    count = await session.scalar(
        select(func.count())
        .select_from(MarketReference)
        .where(
            MarketReference.game == game,
            MarketReference.mode == mode,
            MarketReference.metric == metric,
            MarketReference.active.is_(True),
        )
    )
    assert count == 1


async def test_bucket_is_assigned_once_a_reference_is_active(session):
    game, mode, metric = "chess.lichess", "blitz", "chess_moves"
    # Seed a reference over a plausible blitz-moves population (lower is better).
    pop = [float(v) for v in range(20, 60)]
    ref = rf.build_reference(pop, 3, lower_is_better=True)
    await state.activate_reference(session, ref, game, mode, metric, version=1)

    player = await _make_user(session)
    for i, moves in enumerate([25, 24, 26, 23, 27, 22, 25, 24, 23, 26]):
        await state.record_and_update(
            session, player, "chess.lichess",
            _norm(f"b{i}", moves, created=1_760_000_000_000 + i),
        )
    row = await state.get_market_state(session, player, game, mode, metric)
    assert row.bucket is not None
    assert 0 <= row.bucket < ref.k
    assert row.bucket_version == 1
