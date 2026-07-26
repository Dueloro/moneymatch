"""Contest disputes — file (participant) and resolve (admin).

The trust valve on settlement: a participant who thinks a settled contest graded
wrong files a dispute with a reason; an admin resolves or rejects it and the
outcome is pushed back to the user as a notification. Money movement (a manual
regrade/refund) stays an explicit admin action — resolving a dispute records the
decision, it does not itself move funds.
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
from ..models.user import User
from . import notifications_service

# A contest can only be disputed once it has a graded outcome to contest.
_DISPUTABLE_STATES = {"SETTLED", "PUSHED"}
_RESOLUTIONS = {"resolved", "rejected"}


async def _is_participant(
    session: AsyncSession, match_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    seat = await session.scalar(
        select(MatchPlayer.id).where(
            MatchPlayer.match_id == match_id, MatchPlayer.user_id == user_id
        )
    )
    return seat is not None


async def file_dispute(
    session: AsyncSession, user: User, match: Match, reason: str
) -> Dispute:
    """File a dispute against a settled contest (participant-only, once)."""
    if match.state not in _DISPUTABLE_STATES:
        raise APIError(
            "not_disputable",
            "Only a settled contest can be disputed.",
            status_code=409,
        )
    if not await _is_participant(session, match.id, user.id):
        raise APIError("not_a_player", "You are not in this match.", status_code=403)
    reason = reason.strip()
    if not reason:
        raise APIError("empty_reason", "Tell us what went wrong.", status_code=422)

    dispute = Dispute(match_id=match.id, user_id=user.id, reason=reason)
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
    session: AsyncSession, match_id: uuid.UUID, user_id: uuid.UUID
) -> Dispute | None:
    return await session.scalar(
        select(Dispute).where(Dispute.match_id == match_id, Dispute.user_id == user_id)
    )


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
            "match_id": str(dispute.match_id),
            "status": status,
            "note": dispute.admin_note,
        },
    )
    return dispute
