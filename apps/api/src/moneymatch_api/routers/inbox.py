"""`/inbox` — the Social nav badge and "I've looked" (`seen`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..schemas.notifications import InboxBadgeResponse
from ..services import inbox_service

router = APIRouter(prefix="/inbox", tags=["notifications"])


@router.get("/badge", response_model=InboxBadgeResponse)
async def get_badge(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> InboxBadgeResponse:
    return InboxBadgeResponse(badge=await inbox_service.badge(session, user))


@router.post("/seen", response_model=InboxBadgeResponse)
async def mark_seen(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> InboxBadgeResponse:
    await inbox_service.mark_seen(session, user)
    return InboxBadgeResponse(badge=0)
