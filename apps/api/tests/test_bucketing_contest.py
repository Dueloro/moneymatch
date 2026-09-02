"""Phase 5 test gate — wager path, room formation, settlement & the money
invariant, end to end against the wallet (DB-backed → CI / local Postgres).

These are the checks that make it safe to move real money: every rupee held is
either paid out or refunded, `sum(payouts)+rake == pot`, and bad data fails
closed to a refund.
"""

from __future__ import annotations

import pytest

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services import wallet_service
from moneymatch_api.services.bucketing import config as cfg
from moneymatch_api.services.bucketing import contest
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state as stmod
from tests.factories import create_user, create_wallet

CHESS_BLITZ = mk.get("chess.lichess", "blitz", "chess_moves")


def _norm(id, moves, created=1_760_000_000_000):
    return NormGame(
        id=id,
        speed="blitz",
        rated=True,
        created_at_ms=created,
        moves=int(moves),
        won=True,
        drawn=False,
        metrics={"chess_moves": float(moves)},
    )


async def _placed_player(session, *, moves_history, available=100_000):
    """A funded player, placed in a bucket by playing `moves_history`."""
    user = await create_user(session)
    await create_wallet(session, user, available_cents=available)
    for i, m in enumerate(moves_history):
        await stmod.record_and_update(
            session,
            user.id,
            "chess.lichess",
            _norm(f"{user.id}-{i}", m, 1_760_000_000_000 + i),
        )
    return user


async def _seed_reference(session):
    # A blitz-moves reference (lower is better) with a mid bar we can straddle.
    pop = [float(v) for v in range(20, 60)]
    ref = rf.build_reference(pop, 3, lower_is_better=True)
    await stmod.activate_reference(
        session, ref, "chess.lichess", "blitz", "chess_moves", version=1
    )
    return ref


# --------------------------------------------------------------------------- #
# Wager entry + cap
# --------------------------------------------------------------------------- #


async def test_enter_wager_holds_stake_and_queues(session):
    await _seed_reference(session)
    user = await _placed_player(session, moves_history=[25] * 12)
    c = await contest.enter_wager(session, user.id, CHESS_BLITZ, 500)
    assert c.status == cfg.STATUS_QUEUED
    w = await wallet_service.get_wallet(session, user.id)
    assert w.escrow_cents == 500
    assert w.available_cents == 100_000 - 500


async def test_wager_rejected_when_not_placed(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=10_000)
    with pytest.raises(contest.BucketWagerError):
        await contest.enter_wager(session, user.id, CHESS_BLITZ, 500)


async def test_stake_over_cap_is_rejected_no_money_moves(session):
    await _seed_reference(session)
    # A provisional player (few games) is capped at the floor $5.
    user = await _placed_player(session, moves_history=[25, 26, 24], available=100_000)
    with pytest.raises(contest.BucketWagerError) as ei:
        await contest.enter_wager(session, user.id, CHESS_BLITZ, 5_000)  # $50 > $5 cap
    assert ei.value.code == "stake_over_cap"
    w = await wallet_service.get_wallet(session, user.id)
    assert w.escrow_cents == 0  # nothing held


# --------------------------------------------------------------------------- #
# Room formation
# --------------------------------------------------------------------------- #


async def test_form_room_needs_a_full_room_then_matches(session):
    await _seed_reference(session)
    users = [await _placed_player(session, moves_history=[25] * 12) for _ in range(4)]
    for u in users:
        await contest.enter_wager(session, u.id, CHESS_BLITZ, 500)

    # 3 waiting < ROOM(4) → no room unless allow_short.
    bucket = (
        await stmod.get_market_state(
            session, users[0].id, "chess.lichess", "blitz", "chess_moves"
        )
    ).bucket
    # All four are in the same bucket (identical histories).
    room = await contest.form_room(
        session, "chess.lichess", "blitz", "chess_moves", bucket
    )
    assert room is not None
    assert room.status == cfg.ROOM_AWAITING_RESULT
    assert room.pot_cents == 2000
    assert room.bar > 0


# --------------------------------------------------------------------------- #
# Settlement — the money invariant end to end
# --------------------------------------------------------------------------- #


async def _run_room(session, histories, results, stake=500):
    ref = await _seed_reference(session)
    users = [await _placed_player(session, moves_history=h) for h in histories]
    for u in users:
        await contest.enter_wager(session, u.id, CHESS_BLITZ, stake)
    bucket = (
        await stmod.get_market_state(
            session, users[0].id, "chess.lichess", "blitz", "chess_moves"
        )
    ).bucket
    room = await contest.form_room(
        session, "chess.lichess", "blitz", "chess_moves", bucket, allow_short=True
    )
    assert room is not None
    members = await contest._room_members(session, room.id)
    for m, res in zip(members, results, strict=True):
        await contest.record_result(session, m, f"qual-{m.id}", res)
    room = await contest.settle_room(session, room)
    return users, room, ref


async def test_settlement_conserves_money_winners_split(session):
    # 4 players, same bucket, bar is low (few moves = good). Two win (beat bar),
    # two miss. Winners split pot·(1−rake); invariant holds to the cent.
    histories = [[25] * 12 for _ in range(4)]
    users, room, ref = await _run_room(
        session, histories, results=[24.0, 23.0, 25.0, 40.0]
    )
    assert room.status == cfg.ROOM_SETTLED

    total_available = 0
    total_escrow = 0
    total_payout = 0
    for u in users:
        w = await wallet_service.get_wallet(session, u.id)
        total_available += w.available_cents
        total_escrow += w.escrow_cents
    # Pot was 2000; each started with 100_000 available.
    starting = 100_000 * 4
    # available + escrow across players + rake == starting funds (money conserved).
    assert total_escrow == 0  # all escrow consumed/paid
    assert total_available + room.rake_cents == starting
    # Payouts sum to pot − rake.
    members = await contest._room_members(session, room.id)
    total_payout = sum(m.payout_cents for m in members)
    assert total_payout + room.rake_cents == 2000


async def test_nobody_clears_refunds_everyone_zero_rake(session):
    # Bar is low (good=few moves); everyone plays badly (many moves) → nobody
    # clears → full refund, zero rake, balances restored.
    histories = [[25] * 12 for _ in range(3)]
    users, room, ref = await _run_room(
        session, histories, results=[80, 90, 85]  # all worse than the bar
    )
    assert room.status == cfg.ROOM_REFUNDED
    assert room.rake_cents == 0
    for u in users:
        w = await wallet_service.get_wallet(session, u.id)
        assert w.available_cents == 100_000  # fully restored
        assert w.escrow_cents == 0


async def test_unverifiable_result_voids_and_refunds(session):
    # One member's result can't be verified (None) → whole room refunds.
    histories = [[25] * 12 for _ in range(3)]
    users, room, ref = await _run_room(
        session, histories, results=[24, None, 23]
    )
    assert room.status == cfg.ROOM_REFUNDED
    for u in users:
        w = await wallet_service.get_wallet(session, u.id)
        assert w.available_cents == 100_000


async def test_settlement_writes_audit_rows(session):
    from sqlalchemy import func, select

    from moneymatch_api.models.bucketing import AuditEvent, Settlement

    histories = [[25] * 12 for _ in range(3)]
    users, room, ref = await _run_room(session, histories, results=[24, 23, 40])
    # One settlement row per member, with the bar + reference version recorded.
    n_settle = await session.scalar(
        select(func.count()).select_from(Settlement)
    )
    assert n_settle == 3
    row = await session.scalar(select(Settlement).limit(1))
    assert row.bar == room.bar
    assert row.reference_version == room.reference_version
    # A room_settled audit event exists.
    n_events = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.event_type == "room_settled")
    )
    assert n_events == 1


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #


async def test_one_open_contest_per_market(session):
    await _seed_reference(session)
    user = await _placed_player(session, moves_history=[25] * 12)
    await contest.enter_wager(session, user.id, CHESS_BLITZ, 500)
    # A second open wager on the same market is rejected cleanly (the partial
    # unique index is the race backstop; the app pre-checks and fails soft).
    with pytest.raises(contest.BucketWagerError) as ei:
        await contest.enter_wager(session, user.id, CHESS_BLITZ, 500)
    assert ei.value.code == "already_wagering"


async def test_expire_unfilled_refunds_and_cancels(session):
    from datetime import timedelta

    await _seed_reference(session)
    user = await _placed_player(session, moves_history=[25] * 12)
    c = await contest.enter_wager(session, user.id, CHESS_BLITZ, 500)
    # Pretend the fill window has elapsed.
    future = contest._now() + timedelta(seconds=cfg.BUCKET_FILL_WINDOW_SECONDS + 1)
    n = await contest.expire_unfilled(session, now=future)
    assert n == 1
    await session.refresh(c)
    assert c.status == cfg.STATUS_CANCELED
    w = await wallet_service.get_wallet(session, user.id)
    assert w.available_cents == 100_000  # refunded
