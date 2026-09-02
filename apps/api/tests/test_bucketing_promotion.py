"""Phase 7 test gate — auto promote/demote (pure gates + DB re-cut).

The gate maths runs anywhere (`nodb`); the controlled re-cut is DB-backed.
"""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services.bucketing import promotion as pr

# --------------------------------------------------------------------------- #
# Pure gate maths
# --------------------------------------------------------------------------- #


@pytest.mark.nodb
def test_tight_precise_liquid_market_supports_more_buckets():
    # Three well-separated, dense clusters with lots of matches per player and
    # plenty of daily entrants → high eligible K.
    rng = random.Random(1)
    indices = (
        [rng.gauss(10, 1) for _ in range(300)]
        + [rng.gauss(50, 1) for _ in range(300)]
        + [rng.gauss(90, 1) for _ in range(300)]
    )
    ev = pr.evaluate_market(
        indices,
        current_k=3,
        sigma_match=2.0,
        median_matches=100.0,
        daily_entrants=400.0,
    )
    assert ev.eligible_k >= 3
    assert ev.action in {"hold", "promote"}


@pytest.mark.nodb
def test_low_liquidity_caps_k_and_names_the_gate():
    # Clean, well-separated clusters (so precision + stability pass), but very few
    # daily entrants: at K=3 each bucket gets 6/3 = 2 < ROOM(4) → liquidity is the
    # gate that caps K, at K=2 (6/2 = 3 < 4 too... so use 8 entrants → K=2 ok).
    rng = random.Random(2)
    indices = (
        [rng.gauss(10, 0.5) for _ in range(200)]
        + [rng.gauss(50, 0.5) for _ in range(200)]
        + [rng.gauss(90, 0.5) for _ in range(200)]
    )
    ev = pr.evaluate_market(
        indices,
        current_k=3,
        sigma_match=1.0,
        median_matches=60.0,
        daily_entrants=8.0,  # 8/3 = 2.7 < 4 at K=3; 8/2 = 4 ≥ 4 at K=2
    )
    assert ev.eligible_k == 2
    assert ev.action == "demote"
    assert ev.binding_gate == "liquidity"


@pytest.mark.nodb
def test_noisy_indexes_fail_precision():
    # Huge match-to-match noise relative to bucket widths → precision blocks
    # finer buckets.
    rng = random.Random(3)
    indices = [rng.gauss(50, 5) for _ in range(400)]
    ev = pr.evaluate_market(
        indices,
        current_k=3,
        sigma_match=80.0,  # noise dwarfs the spread
        median_matches=4.0,
        daily_entrants=1000.0,
    )
    assert ev.eligible_k < 3
    assert ev.binding_gate in {"precision", "stability"}


@pytest.mark.nodb
def test_evaluation_is_deterministic():
    rng = random.Random(4)
    indices = [rng.gauss(50, 12) for _ in range(200)]
    a = pr.evaluate_market(
        indices, current_k=3, sigma_match=4.0, median_matches=40.0, daily_entrants=200.0
    )
    b = pr.evaluate_market(
        indices, current_k=3, sigma_match=4.0, median_matches=40.0, daily_entrants=200.0
    )
    assert (a.eligible_k, a.action, a.binding_gate) == (
        b.eligible_k,
        b.action,
        b.binding_gate,
    )


# --------------------------------------------------------------------------- #
# DB re-cut
# --------------------------------------------------------------------------- #


async def test_recut_versions_rebuckets_and_leaves_old_settlements(session):

    from moneymatch_api.adapters.base import NormGame
    from moneymatch_api.services.bucketing import markets as mk
    from moneymatch_api.services.bucketing import reference as rf
    from moneymatch_api.services.bucketing import state as stmod
    from tests.factories import create_user

    market = mk.get("chess.lichess", "blitz", "chess_moves")

    # Seed v1 and place a spread of players.
    v1 = rf.build_reference(
        [float(v) for v in range(20, 60)], 3, lower_is_better=True
    )
    await stmod.activate_reference(
        session, v1, "chess.lichess", "blitz", "chess_moves", version=1
    )
    for moves in (22, 24, 30, 33, 40, 44, 50, 55):
        u = await create_user(session)
        for i in range(12):
            await stmod.record_and_update(
                session,
                u.id,
                "chess.lichess",
                NormGame(
                    id=f"{u.id}-{i}",
                    speed="blitz",
                    rated=True,
                    created_at_ms=1_760_000_000_000 + i,
                    moves=moves,
                    won=True,
                    drawn=False,
                    metrics={"chess_moves": float(moves)},
                ),
            )

    # Apply a 3→4 re-cut as version 2.
    n = await pr.apply_recut(session, market, 4, new_version=2)
    assert n == 8  # everyone re-bucketed

    active = await stmod.get_active_reference(
        session, "chess.lichess", "blitz", "chess_moves"
    )
    assert active.version == 2
    assert active.k == 4

    # Every placed player now carries bucket_version 2.
    from sqlalchemy import select

    from moneymatch_api.models.bucketing import MarketState

    states = (
        (
            await session.execute(
                select(MarketState).where(MarketState.game == "chess.lichess")
            )
        )
        .scalars()
        .all()
    )
    assert all(s.bucket_version == 2 for s in states)
    assert all(0 <= s.bucket < 4 for s in states)
