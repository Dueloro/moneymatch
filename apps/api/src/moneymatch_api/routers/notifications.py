"""`/notifications` — the Inbox feed and mark-read (design PDF p.11).

Reading the Inbox also bumps the presence heartbeat (this is a polled surface).
Mark-read is idempotent (08-phase-5 · deliverable 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..schemas.notifications import (
    MarkReadRequest,
    MarkReadResponse,
    NotificationItem,
    NotificationsResponse,
)
from ..services import friends_service, notifications_service, push_service

router = APIRouter(tags=["notifications"])


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class PushPublicKeyResponse(BaseModel):
    # The VAPID application-server public key (base64url), or null when push is
    # not configured — the client then hides the "enable notifications" control.
    public_key: str | None


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


@router.get("/notifications/push/public-key", response_model=PushPublicKeyResponse)
async def push_public_key(_user: CurrentUser) -> PushPublicKeyResponse:
    return PushPublicKeyResponse(public_key=push_service.public_key())


@router.post("/notifications/push/subscribe", status_code=204)
async def push_subscribe(
    body: PushSubscribeRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> None:
    await push_service.subscribe(
        session,
        user.id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
    )


@router.post("/notifications/push/unsubscribe", status_code=204)
async def push_unsubscribe(
    body: PushUnsubscribeRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> None:
    await push_service.unsubscribe(session, user.id, body.endpoint)
