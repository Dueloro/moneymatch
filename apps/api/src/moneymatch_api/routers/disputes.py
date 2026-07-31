"""`/disputes` — file / read a contest dispute for any contest type.

The polymorphic sibling of the match-only `/play/matches/{id}/dispute` shim: the
Activity feed's "Contest" action posts here with `{ref_type, ref_id, reason}` so
one code path serves matches, pools, and tournaments.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..schemas.play import ContestRequest, DisputeView
from ..services import dispute_service

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.post("", response_model=DisputeView, status_code=201)
async def file_contest_dispute(
    body: ContestRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> DisputeView:
    """Contest how a settled contest (match/pool/tournament) was graded."""
    dispute = await dispute_service.file_dispute(
        session, user, body.ref_type, body.ref_id, body.reason
    )
    return DisputeView.model_validate(dispute)


@router.get("/{ref_type}/{ref_id}", response_model=DisputeView | None)
async def get_contest_dispute(
    ref_type: str,
    ref_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> DisputeView | None:
    """The viewer's dispute for this contest, if any."""
    dispute = await dispute_service.get_for(session, ref_type, ref_id, user.id)
    return DisputeView.model_validate(dispute) if dispute else None
