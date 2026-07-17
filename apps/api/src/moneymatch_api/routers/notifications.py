"""`/notifications` — the Inbox feed and mark-read (design PDF p.11).

Reading the Inbox also bumps the presence heartbeat (this is a polled surface).
Mark-read is idempotent (08-phase-5 · deliverable 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..schemas.notifications import (
    MarkReadRequest,
    MarkReadResponse,
    NotificationItem,
    NotificationsResponse,
)
from ..services import friends_service, notifications_service

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationsResponse)
async def get_notifications(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> NotificationsResponse:
    await friends_service.heartbeat(session, user)
    rows = await notifications_service.list_for_user(session, user.id)
    unread = await notifications_service.unread_count(session, user.id)
    return NotificationsResponse(
        unread=unread,
        items=[
            NotificationItem(
                id=r.id,
                kind=r.kind,
                payload=r.payload,
                read=r.read_at is not None,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.post("/notifications/read", response_model=MarkReadResponse)
async def mark_read(
    body: MarkReadRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MarkReadResponse:
    unread = await notifications_service.mark_read(session, user.id, ids=body.ids)
    return MarkReadResponse(unread=unread)
