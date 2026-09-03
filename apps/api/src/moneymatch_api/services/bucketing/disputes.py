"""Phase 6 — disputes & audit reconstruction.

Two capabilities:

1. **Reconstruction (`explain_contest`)** — reassemble the full grading story of a
   settled contest purely from stored rows: the player's settlement row, the
   `market_reference` version that was active *at settlement time* (read off the
   settlement row, never "current"), that version's cut points and bar, the
   result, and the payout arithmetic. Because Phases 3/5 versioned everything,
   this is always a lookup — even after the market has been re-cut, an old contest
   still explains itself with the ruler it was graded by.

2. **Dispute lifecycle** — open (snapshot evidence + place a hold), then an admin
   resolves to no_change / refund / adjust. Every transition also writes an
   `audit_events` row (with `actor='admin'` for admin actions), so the trail can't
   be quietly edited. A resolved_refund returns the player's stake.

All DB I/O; flush-not-commit, like the rest of the layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...errors import APIError
from ...models.bucket_contest import BucketContest, BucketRoom
from ...models.bucket_dispute import BucketDispute
from ...models.bucketing import AuditEvent, MarketReference, MatchStat, Settlement
from ...services import wallet_service
from . import config as cfg


class DisputeError(APIError):
    """A dispute action was rejected."""


def _now() -> datetime:
    return datetime.now(UTC)


async def _audit(session: AsyncSession, **kw) -> None:
    # The sessionmaker runs with autoflush=False, so flush the audit row here —
    # a caller (or a read on the same session) must see it without a manual flush.
    session.add(AuditEvent(**kw))
    await session.flush()


# --------------------------------------------------------------------------- #
# Reconstruction
# --------------------------------------------------------------------------- #


async def explain_contest(session: AsyncSession, contest_id: uuid.UUID) -> dict:
    """Reconstruct how a contest graded, entirely from stored versioned rows.

    Raises `DisputeError` if there is no settlement for the contest yet.
    """
    contest = await session.get(BucketContest, contest_id)
    if contest is None:
        raise DisputeError("contest_not_found", "No such contest.", status_code=404)

    settlement = await session.scalar(
        select(Settlement).where(Settlement.contest_id == str(contest_id))
    )
    if settlement is None:
        raise DisputeError(
            "not_settled",
            "This contest has not settled yet — nothing to explain.",
            status_code=409,
        )

    # The reference version that was active *at settlement time* — read off the
    # settlement row, not the current active version. This is the crux of version
    # isolation: a later re-cut never changes this reconstruction.
    ref = await session.scalar(
        select(MarketReference).where(
            MarketReference.game == settlement.game,
            MarketReference.mode == settlement.mode,
            MarketReference.metric == settlement.metric,
            MarketReference.season == settlement.reference_season,
            MarketReference.version == settlement.reference_version,
        )
    )

    return {
        "contest_id": str(contest_id),
        "player_id": str(settlement.player_id),
        "market": f"{settlement.game}:{settlement.mode}:{settlement.metric}",
        "bucket": settlement.bucket,
        "bar": settlement.bar,
        "reference": {
            "season": settlement.reference_season,
            "version": settlement.reference_version,
            "cut_points": list(ref.cuts) if ref else None,
            "bucket_bar": (
                ref.bars[settlement.bucket]
                if ref and settlement.bucket < len(ref.bars)
                else settlement.bar
            ),
            "lower_is_better": ref.lower_is_better if ref else None,
            "source": ref.source if ref else None,
        },
        "result_value": settlement.result_value,
        "cleared": settlement.cleared,
        "money": {
            "stake_cents": settlement.stake_cents,
            "payout_cents": settlement.payout_cents,
            "rake_cents": settlement.rake_cents,
            "refunded": settlement.refunded,
        },
        # A plain-language line the UI can show.
        "explanation": _explain_line(settlement, ref),
    }


def _explain_line(s: Settlement, ref: MarketReference | None) -> str:
    lower = ref.lower_is_better if ref else False
    cmp = "at most" if lower else "at least"
    if s.refunded:
        return f"Refunded — the contest was voided (bar was {cmp} {s.bar:g})."
    if s.cleared:
        return (
            f"You cleared the bar ({cmp} {s.bar:g}) with {s.result_value:g} and "
            f"won {s.payout_cents} cents."
        )
    return (
        f"You needed {cmp} {s.bar:g} but produced {s.result_value:g}, so the "
        "wager did not clear."
    )


# --------------------------------------------------------------------------- #
# Dispute lifecycle
# --------------------------------------------------------------------------- #


async def open_dispute(
    session: AsyncSession,
    contest_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    *,
    place_hold: bool = True,
) -> BucketDispute:
    """Open a dispute: snapshot the settlement + audit evidence (immutable), place
    an optional hold, and write an audit event. Only the contest's own player may
    dispute it, and only once."""
    contest = await session.get(BucketContest, contest_id)
    if contest is None:
        raise DisputeError("contest_not_found", "No such contest.", status_code=404)
    if contest.player_id != user_id:
        raise DisputeError(
            "not_your_contest",
            "You can only dispute your own contest.",
            status_code=403,
        )

    existing = await session.scalar(
        select(BucketDispute.id).where(
            BucketDispute.contest_id == contest_id,
            BucketDispute.user_id == user_id,
        )
    )
    if existing is not None:
        raise DisputeError(
            "already_disputed",
            "You have already disputed this contest.",
            status_code=409,
        )

    # Snapshot the evidence so later recomputes can't alter it.
    evidence = await _snapshot_evidence(session, contest_id)

    dispute = BucketDispute(
        contest_id=contest_id,
        user_id=user_id,
        reason=reason,
        status="open",
        evidence=evidence,
        hold=place_hold,
    )
    session.add(dispute)
    await session.flush()
    await _audit(
        session,
        player_id=user_id,
        event_type="dispute_opened",
        contest_id=str(contest_id),
        after={"dispute_id": str(dispute.id), "hold": place_hold},
        reason=reason,
    )
    return dispute


async def _snapshot_evidence(session: AsyncSession, contest_id: uuid.UUID) -> dict:
    settlement = await session.scalar(
        select(Settlement).where(Settlement.contest_id == str(contest_id))
    )
    events = (
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.contest_id == str(contest_id))
                .order_by(AuditEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    snap: dict = {"settlement": None, "audit_events": []}
    if settlement is not None:
        snap["settlement"] = {
            "bucket": settlement.bucket,
            "bar": settlement.bar,
            "reference_season": settlement.reference_season,
            "reference_version": settlement.reference_version,
            "result_value": settlement.result_value,
            "cleared": settlement.cleared,
            "stake_cents": settlement.stake_cents,
            "payout_cents": settlement.payout_cents,
            "refunded": settlement.refunded,
        }
    snap["audit_events"] = [
        {"event_type": e.event_type, "after": e.after, "at": e.created_at.isoformat()}
        for e in events
    ]
    return snap


async def resolve_dispute(
    session: AsyncSession,
    dispute_id: uuid.UUID,
    resolution: str,
    *,
    admin: str,
    note: str | None = None,
) -> BucketDispute:
    """Resolve a dispute (admin). `resolution` is one of resolved_no_change /
    resolved_refund / resolved_adjust. A refund returns the player's stake and
    releases the hold; every resolution writes an admin-actor audit event."""
    valid = {"resolved_no_change", "resolved_refund", "resolved_adjust"}
    if resolution not in valid:
        raise DisputeError(
            "invalid_resolution", f"Resolution must be one of {sorted(valid)}.",
            status_code=422,
        )
    dispute = await session.get(BucketDispute, dispute_id)
    if dispute is None:
        raise DisputeError("dispute_not_found", "No such dispute.", status_code=404)
    if dispute.status.startswith("resolved"):
        raise DisputeError(
            "already_resolved", "This dispute is already resolved.", status_code=409
        )

    contest = await session.get(BucketContest, dispute.contest_id)

    if resolution == "resolved_refund" and contest is not None:
        # A dispute is resolved *after* settlement, so the stake escrow is already
        # gone (consumed into the pot, or refunded on a void). Returning it now is
        # a platform-funded correction — `credit`, not `refund` (which would
        # manipulate an escrow balance that no longer exists). Idempotency guard:
        # only credit once.
        if contest.status != cfg.STATUS_REFUNDED:
            await wallet_service.credit(
                session,
                contest.player_id,
                contest.stake_cents,
                memo=f"dispute {dispute_id} refund",
                created_by=admin,
                ref_id=contest.id,
            )
            contest.status = cfg.STATUS_REFUNDED
            contest.payout_cents = contest.stake_cents

    dispute.status = resolution
    dispute.admin_note = note
    dispute.hold = False  # resolving releases the hold
    dispute.resolved_at = _now()
    await session.flush()
    await _audit(
        session,
        player_id=dispute.user_id,
        event_type="dispute_resolved",
        contest_id=str(dispute.contest_id),
        after={"dispute_id": str(dispute.id), "resolution": resolution},
        actor="admin",
        reason=note,
    )
    return dispute


async def is_held(session: AsyncSession, contest_id: uuid.UUID) -> bool:
    """Whether an open dispute is holding this contest's payout/withdrawal."""
    held = await session.scalar(
        select(BucketDispute.id).where(
            BucketDispute.contest_id == contest_id,
            BucketDispute.hold.is_(True),
        )
    )
    return held is not None


# --------------------------------------------------------------------------- #
# Room evidence + fault-based clawback
# --------------------------------------------------------------------------- #


async def explain_room(session: AsyncSession, room_id: uuid.UUID) -> dict:
    """Everything an admin needs to decide who was unfair in a room.

    For each member: what they wagered (stake), the bar they had to beat, the
    result they actually produced, whether it cleared, their payout — and the
    **full recorded stat line** of their qualifying match from `match_stats` (the
    complete metrics the adapter saw, not just the wagered one). This is the
    "check the log to see who was unfair" surface: compare a suspicious result to
    the rest of the room and to that player's own recorded stats.

    Fault is still an admin judgement (and can be informed by the Phase-8 anomaly
    flags); this function only lays out the evidence.
    """
    room = await session.get(BucketRoom, room_id)
    if room is None:
        raise DisputeError("room_not_found", "No such room.", status_code=404)

    members = (
        (
            await session.execute(
                select(BucketContest).where(BucketContest.room_id == room_id)
            )
        )
        .scalars()
        .all()
    )
    rows = []
    for m in members:
        match_stats = None
        if m.qualifying_match_id:
            ms = await session.scalar(
                select(MatchStat).where(
                    MatchStat.player_id == m.player_id,
                    MatchStat.host_match_id == m.qualifying_match_id,
                )
            )
            match_stats = ms.metrics if ms else None
        rows.append(
            {
                "contest_id": str(m.id),
                "player_id": str(m.player_id),
                "stake_cents": m.stake_cents,
                "bar": m.bar if m.bar is not None else room.bar,
                "result_value": m.result_value,
                "cleared": m.cleared,
                "payout_cents": m.payout_cents,
                "qualifying_match_id": m.qualifying_match_id,
                "match_stats": match_stats,  # the full recorded stat line
            }
        )
    return {
        "room_id": str(room_id),
        "market": f"{room.game}:{room.mode}:{room.metric}",
        "bucket": room.bucket,
        "bar": room.bar,
        "lower_is_better": room.lower_is_better,
        "members": rows,
    }


async def resolve_with_clawback(
    session: AsyncSession,
    dispute_id: uuid.UUID,
    fault_player_ids: list[uuid.UUID],
    *,
    admin: str,
    note: str | None = None,
) -> BucketDispute:
    """Resolve a dispute by **voiding the tainted contest and making the unfair
    player(s) pay** — the money goes back to the honest players from the cheater's
    pocket, not the platform's.

    What it does, for the room the disputed contest belongs to:

    1. **Claw back every payout** that was made in the room (the results are
       tainted, so no winnings stand) — recovered from each player's wallet,
       best-effort (a wallet can't go negative, so it recovers up to what's
       there).
    2. **Refund every honest player their stake** in full — they are always made
       whole.
    3. The **fault player(s) forfeit**: their winnings are clawed back and their
       stake is not returned.

    Funding order is exactly what you asked for: the honest players' refunds are
    paid out of what is recovered from the unfair player(s); the platform only
    covers a shortfall if a cheater's wallet is already empty (so a victim is
    never left short). Every cent — recovered, refunded, and any platform
    backstop — is written to `audit_events`.
    """
    dispute = await session.get(BucketDispute, dispute_id)
    if dispute is None:
        raise DisputeError("dispute_not_found", "No such dispute.", status_code=404)
    if dispute.status.startswith("resolved"):
        raise DisputeError(
            "already_resolved", "This dispute is already resolved.", status_code=409
        )

    contest = await session.get(BucketContest, dispute.contest_id)
    if contest is None or contest.room_id is None:
        raise DisputeError(
            "not_matched",
            "A clawback needs a matched contest (a room to void).",
            status_code=409,
        )

    members = (
        (
            await session.execute(
                select(BucketContest).where(BucketContest.room_id == contest.room_id)
            )
        )
        .scalars()
        .all()
    )
    member_players = {m.player_id for m in members}
    fault_set = set(fault_player_ids)
    if not fault_set or not fault_set <= member_players:
        raise DisputeError(
            "invalid_fault",
            "Every fault player must be a member of the contest's room.",
            status_code=422,
        )

    # (1) Claw back every payout in the room (void the tainted results).
    recovered = 0
    for m in members:
        if m.payout_cents and m.payout_cents > 0:
            wallet = await wallet_service.get_wallet_or_none(session, m.player_id)
            available = wallet.available_cents if wallet else 0
            take = min(m.payout_cents, available)
            if take > 0:
                await wallet_service.debit(
                    session,
                    m.player_id,
                    take,
                    memo=f"clawback (dispute {dispute_id})",
                    created_by=admin,
                    ref_id=m.id,
                )
                recovered += take

    # (2) Refund every honest player their full stake; (3) fault players forfeit.
    refunded = 0
    for m in members:
        if m.player_id in fault_set:
            m.status = cfg.STATUS_REFUNDED
            m.payout_cents = 0  # forfeit: no winnings, no stake back
            m.settled_at = _now()
            continue
        await wallet_service.credit(
            session,
            m.player_id,
            m.stake_cents,
            memo=f"clawback refund (dispute {dispute_id})",
            created_by=admin,
            ref_id=m.id,
        )
        m.status = cfg.STATUS_REFUNDED
        m.payout_cents = m.stake_cents
        m.settled_at = _now()
        refunded += m.stake_cents

    shortfall = max(0, refunded - recovered)

    dispute.status = "resolved_adjust"
    dispute.admin_note = note
    dispute.hold = False
    dispute.resolved_at = _now()
    await session.flush()
    await _audit(
        session,
        player_id=dispute.user_id,
        event_type="dispute_clawback",
        contest_id=str(dispute.contest_id),
        after={
            "dispute_id": str(dispute.id),
            "fault_players": [str(p) for p in fault_set],
            "recovered_from_fault_cents": recovered,
            "refunded_to_honest_cents": refunded,
            "platform_backstop_cents": shortfall,
        },
        actor="admin",
        reason=note,
    )
    return dispute
