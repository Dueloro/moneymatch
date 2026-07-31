"""Contest disputes — file (participant) and resolve (admin).

The trust valve on settlement: a participant who thinks a settled contest graded
wrong files a dispute with a reason; an admin resolves or rejects it and the
outcome is pushed back to the user as a notification. Money movement (a manual
regrade/refund) stays an explicit admin action — resolving a dispute records the
decision, it does not itself move funds.

Disputes are **polymorphic**: a `(ref_type, ref_id)` pair points at a match, a
solo pool, or a tournament. There is no single FK target, so this module owns the
"is this a real, settled contest the user actually played?" check for each type.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import APIError
from ..models.dispute import Dispute
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from . import notifications_service

# A contest can only be disputed once it has a graded outcome to contest.
_DISPUTABLE_MATCH_STATES = {"SETTLED", "PUSHED"}
_DISPUTABLE_CONTEST_STATES = {"SETTLED", "CANCELED"}
_RESOLUTIONS = {"resolved", "rejected"}
_REF_TYPES = ("match", "pool", "tournament")


async def _match_participant(
    session: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[bool, bool]:
    """(is_disputable, is_participant) for a match ref."""
    match = await session.get(Match, ref_id)
    if match is None:
        raise APIError("not_found", "Contest not found.", status_code=404)
    seat = await session.scalar(
        select(MatchPlayer.id).where(
            MatchPlayer.match_id == ref_id, MatchPlayer.user_id == user_id
        )
    )
    return match.state in _DISPUTABLE_MATCH_STATES, seat is not None


async def _pool_participant(
    session: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[bool, bool]:
    pool = await session.get(SoloPool, ref_id)
    if pool is None:
        raise APIError("not_found", "Contest not found.", status_code=404)
    entry = await session.scalar(
        select(SoloEntry.id).where(
            SoloEntry.pool_id == ref_id, SoloEntry.user_id == user_id
        )
    )
    return pool.state in _DISPUTABLE_CONTEST_STATES, entry is not None


async def _tournament_participant(
    session: AsyncSession, ref_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[bool, bool]:
    tournament = await session.get(Tournament, ref_id)
    if tournament is None:
        raise APIError("not_found", "Contest not found.", status_code=404)
    entry = await session.scalar(
        select(TournamentEntry.id).where(
            TournamentEntry.tournament_id == ref_id,
            TournamentEntry.user_id == user_id,
        )
    )
    return tournament.state in _DISPUTABLE_CONTEST_STATES, entry is not None


_CHECKS = {
    "match": _match_participant,
    "pool": _pool_participant,
    "tournament": _tournament_participant,
}


async def file_dispute(
    session: AsyncSession,
    user: User,
    ref_type: str,
    ref_id: uuid.UUID,
    reason: str,
) -> Dispute:
    """File a dispute against a settled contest (participant-only, once).

    Works for any contest type; the per-type check enforces "you were in it" and
    "it has a graded outcome to contest"."""
    if ref_type not in _CHECKS:
        raise APIError("bad_ref_type", "Unknown contest type.", status_code=422)
    disputable, is_participant = await _CHECKS[ref_type](session, ref_id, user.id)
    if not is_participant:
        raise APIError("not_a_player", "You are not in this contest.", status_code=403)
    if not disputable:
        raise APIError(
            "not_disputable",
            "Only a settled contest can be disputed.",
            status_code=409,
        )
    reason = reason.strip()
    if not reason:
        raise APIError("empty_reason", "Tell us what went wrong.", status_code=422)

    dispute = Dispute(ref_type=ref_type, ref_id=ref_id, user_id=user.id, reason=reason)
    session.add(dispute)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise APIError(
            "already_disputed",
            "You've already disputed this contest.",
            status_code=409,
        ) from exc
    return dispute


async def get_for(
    session: AsyncSession,
    ref_type: str,
    ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Dispute | None:
    return await session.scalar(
        select(Dispute).where(
            Dispute.ref_type == ref_type,
            Dispute.ref_id == ref_id,
            Dispute.user_id == user_id,
        )
    )


async def statuses_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[tuple[str, uuid.UUID], str]:
    """Every dispute the user has filed, keyed by (ref_type, ref_id) → status.

    One query so the Activity feed can flag "already contested" without an N+1."""
    rows = await session.execute(
        select(Dispute.ref_type, Dispute.ref_id, Dispute.status).where(
            Dispute.user_id == user_id
        )
    )
    return {(rt, rid): status for rt, rid, status in rows}


async def list_open(session: AsyncSession) -> list[Dispute]:
    return list(
        await session.scalars(
            select(Dispute).where(Dispute.status == "open").order_by(Dispute.created_at)
        )
    )


async def resolve(
    session: AsyncSession,
    dispute_id: uuid.UUID,
    *,
    status: str,
    note: str | None = None,
) -> Dispute:
    """Admin resolves/rejects a dispute and the user is notified."""
    if status not in _RESOLUTIONS:
        raise APIError(
            "invalid_status",
            "Resolution must be 'resolved' or 'rejected'.",
            status_code=422,
        )
    dispute = await session.get(Dispute, dispute_id)
    if dispute is None:
        raise APIError("not_found", "Dispute not found.", status_code=404)

    dispute.status = status
    dispute.admin_note = (note or "").strip() or None
    dispute.resolved_at = datetime.now(UTC)
    await session.flush()

    await notifications_service.emit(
        session,
        dispute.user_id,
        kind="dispute_resolved",
        payload={
            "dispute_id": str(dispute.id),
            "ref_type": dispute.ref_type,
            "ref_id": str(dispute.ref_id),
            "status": status,
            "note": dispute.admin_note,
        },
    )
    return dispute
