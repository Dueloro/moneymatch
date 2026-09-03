"""Phase 6 test gate — disputes & audit reconstruction (DB-backed → CI / local).

The headline: a contest settled under reference version 1 still reconstructs with
version 1's cut points and bar even after the market is re-cut to version 2 —
end-to-end version isolation.
"""

from __future__ import annotations

import pytest

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services import wallet_service
from moneymatch_api.services.bucketing import contest, disputes
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state as stmod
from tests.factories import create_user, create_wallet

CHESS_BLITZ = mk.get("chess.lichess", "blitz", "chess_moves")


def _norm(id, moves, created=1_760_000_000_000):
    return NormGame(
        id=id, speed="blitz", rated=True, created_at_ms=created,
        moves=int(moves), won=True, drawn=False,
        metrics={"chess_moves": float(moves)},
    )


async def _placed(session, moves, available=100_000):
    u = await create_user(session)
    await create_wallet(session, u, available_cents=available)
    for i, m in enumerate(moves):
        await stmod.record_and_update(
            session,
            u.id,
            "chess.lichess",
            _norm(f"{u.id}-{i}", m, 1_760_000_000_000 + i),
        )
    return u


async def _settled_room(session, results):
    ref = rf.build_reference(
        [float(v) for v in range(20, 60)], 3, lower_is_better=True
    )
    await stmod.activate_reference(
        session, ref, "chess.lichess", "blitz", "chess_moves", version=1
    )
    users = [await _placed(session, [25] * 12) for _ in results]
    for u in users:
        await contest.enter_wager(session, u.id, CHESS_BLITZ, 500)
    bucket = (
        await stmod.get_market_state(
            session, users[0].id, "chess.lichess", "blitz", "chess_moves"
        )
    ).bucket
    room = await contest.form_room(
        session, "chess.lichess", "blitz", "chess_moves", bucket, allow_short=True
    )
    members = await contest._room_members(session, room.id)
    for m, r in zip(members, results, strict=True):
        qid = f"qual-{m.id}"
        if r is not None:
            # Ingest the qualifying match through the real path, so its full stat
            # line lands in match_stats (what explain_room reads as evidence).
            await stmod.record_and_update(
                session,
                m.player_id,
                "chess.lichess",
                _norm(qid, int(r), created=1_760_000_100_000),
            )
        await contest.record_result(session, m, qid, r)
    await contest.settle_room(session, room)
    return users, members, room


# --------------------------------------------------------------------------- #
# Reconstruction + version isolation
# --------------------------------------------------------------------------- #


async def test_explain_reconstructs_from_stored_rows(session):
    _users, members, room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    story = await disputes.explain_contest(session, members[0].id)
    assert story["bar"] == room.bar
    assert story["reference"]["version"] == 1
    assert story["reference"]["cut_points"] is not None
    assert "cleared" in story
    assert isinstance(story["explanation"], str)


async def test_reconstruction_uses_the_historical_reference_after_a_recut(session):
    _users, members, room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    old_bar = room.bar

    # Re-cut the market to a NEW version 2 with a different population → new bars.
    new_ref = rf.build_reference(
        [float(v) for v in range(10, 90)], 3, lower_is_better=True
    )
    await stmod.activate_reference(
        session, new_ref, "chess.lichess", "blitz", "chess_moves", version=2
    )

    # The old contest still explains itself with version 1's ruler.
    story = await disputes.explain_contest(session, members[0].id)
    assert story["reference"]["version"] == 1  # NOT the now-active version 2
    assert story["bar"] == old_bar
    # And the version-1 reference row is what was read (its cut points).
    assert story["reference"]["cut_points"] is not None


# --------------------------------------------------------------------------- #
# Dispute lifecycle
# --------------------------------------------------------------------------- #


async def test_open_dispute_snapshots_evidence_and_holds(session):
    users, members, _room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    # The player who lost disputes.
    loser = next(m for m in members if not m.cleared)
    d = await disputes.open_dispute(
        session, loser.id, loser.player_id, "host disconnect", place_hold=True
    )
    assert d.status == "open"
    assert d.hold is True
    assert d.evidence["settlement"] is not None  # snapshot captured
    assert await disputes.is_held(session, loser.id) is True


async def test_only_the_owner_can_dispute(session):
    users, members, _room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    other = await create_user(session)
    with pytest.raises(disputes.DisputeError) as ei:
        await disputes.open_dispute(session, members[0].id, other.id, "not mine")
    assert ei.value.code == "not_your_contest"


async def test_cannot_dispute_twice(session):
    _users, members, _room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    m = members[0]
    await disputes.open_dispute(session, m.id, m.player_id, "first")
    with pytest.raises(disputes.DisputeError) as ei:
        await disputes.open_dispute(session, m.id, m.player_id, "again")
    assert ei.value.code == "already_disputed"


async def test_resolve_refund_returns_stake_and_releases_hold(session):
    users, members, _room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    loser = next(m for m in members if not m.cleared)
    before = (await wallet_service.get_wallet(session, loser.player_id)).available_cents
    d = await disputes.open_dispute(session, loser.id, loser.player_id, "disconnect")

    resolved = await disputes.resolve_dispute(
        session, d.id, "resolved_refund", admin="admin-1", note="host was down"
    )
    assert resolved.status == "resolved_refund"
    assert resolved.hold is False
    after = (await wallet_service.get_wallet(session, loser.player_id)).available_cents
    assert after == before + loser.stake_cents  # stake returned
    assert await disputes.is_held(session, loser.id) is False


async def test_resolve_no_change_keeps_the_result(session):
    _users, members, _room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    m = members[0]
    d = await disputes.open_dispute(session, m.id, m.player_id, "just checking")
    resolved = await disputes.resolve_dispute(
        session, d.id, "resolved_no_change", admin="admin-1"
    )
    assert resolved.status == "resolved_no_change"
    assert resolved.hold is False


async def test_admin_resolution_is_audited(session):
    from sqlalchemy import func, select

    from moneymatch_api.models.bucketing import AuditEvent

    _users, members, _room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    m = members[0]
    d = await disputes.open_dispute(session, m.id, m.player_id, "x")
    await disputes.resolve_dispute(session, d.id, "resolved_no_change", admin="admin-9")
    n = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.event_type == "dispute_resolved", AuditEvent.actor == "admin")
    )
    assert n == 1


async def test_explain_room_lays_out_the_evidence(session):
    _users, members, room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    ev = await disputes.explain_room(session, room.id)
    assert len(ev["members"]) == 3
    row = ev["members"][0]
    # Everything an admin needs to judge fault: wager, bar, result, and the full
    # recorded stat line from the match log.
    assert set(row) >= {
        "player_id",
        "stake_cents",
        "bar",
        "result_value",
        "cleared",
        "match_stats",
    }
    assert row["match_stats"] is not None
    assert "chess_moves" in row["match_stats"]


async def test_clawback_refunds_honest_players_from_the_cheaters_pocket(session):
    # 3 players stake $5. The cheater posts a great (low-moves) result and wins;
    # the two honest players lose. Admin finds the winner was unfair → clawback.
    users, members, room = await _settled_room(session, results=[20.0, 60.0, 62.0])
    winner = next(m for m in members if m.cleared)
    losers = [m for m in members if not m.cleared]
    assert len(losers) == 2

    # The winner actually got paid (their available rose above the 100_000 start).
    w_before = await wallet_service.get_wallet(session, winner.player_id)
    assert w_before.available_cents > 100_000

    # Open a dispute (by an honest player) and clawback with the winner at fault.
    d = await disputes.open_dispute(
        session, losers[0].id, losers[0].player_id, "opponent was cheating"
    )
    await disputes.resolve_with_clawback(
        session, d.id, [winner.player_id], admin="admin-7", note="confirmed boosting"
    )

    # Honest players are made whole — exactly their stake back, nothing lost.
    for m in losers:
        w = await wallet_service.get_wallet(session, m.player_id)
        assert w.available_cents == 100_000

    # The cheater forfeits: winnings clawed back AND stake gone → down their stake.
    w_after = await wallet_service.get_wallet(session, winner.player_id)
    assert w_after.available_cents == 100_000 - winner.stake_cents
    fault_contest = await session.get(type(winner), winner.id)
    assert fault_contest.payout_cents == 0


async def test_clawback_audits_the_money_flow(session):
    from sqlalchemy import select

    from moneymatch_api.models.bucketing import AuditEvent

    users, members, room = await _settled_room(session, results=[20.0, 60.0, 62.0])
    winner = next(m for m in members if m.cleared)
    loser = next(m for m in members if not m.cleared)
    d = await disputes.open_dispute(session, loser.id, loser.player_id, "unfair")
    await disputes.resolve_with_clawback(
        session, d.id, [winner.player_id], admin="admin-7"
    )
    ev = await session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "dispute_clawback")
    )
    assert ev is not None
    assert ev.actor == "admin"
    # The refund to honest players was funded by what was recovered from the
    # cheater — the recovered amount covers the refunds (no platform backstop).
    assert ev.after["recovered_from_fault_cents"] >= ev.after["refunded_to_honest_cents"]
    assert ev.after["platform_backstop_cents"] == 0


async def test_evidence_snapshot_is_immutable_after_later_recut(session):
    _users, members, room = await _settled_room(session, results=[24.0, 40.0, 23.0])
    m = members[0]
    d = await disputes.open_dispute(session, m.id, m.player_id, "x")
    snap_bar = d.evidence["settlement"]["bar"]

    # A later re-cut changes the market, but the snapshot must not move.
    new_ref = rf.build_reference(
        [float(v) for v in range(10, 90)], 3, lower_is_better=True
    )
    await stmod.activate_reference(
        session, new_ref, "chess.lichess", "blitz", "chess_moves", version=2
    )
    await session.refresh(d)
    assert d.evidence["settlement"]["bar"] == snap_bar == room.bar
