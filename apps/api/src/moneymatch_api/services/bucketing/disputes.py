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
from ...models.bucket_contest import BucketContest
from ...models.bucket_dispute import BucketDispute
from ...models.bucketing import AuditEvent, MarketReference, Settlement
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
