"""`/admin/support` — read and reply to user support threads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...models.chat import MAX_MESSAGE_CHARS, Message
from ...services import admin_audit_service, admin_support_service, email_service
from ...services.support_mail import reply_address

router = APIRouter(prefix="/support", tags=["admin"])


class SupportThreadItem(BaseModel):
    conversation_id: UUID
    user_id: UUID
    username: str | None
    email: str | None
    last_message_at: datetime | None
    last_message_preview: str | None
    awaiting_reply: bool


class SupportMessageItem(BaseModel):
    id: UUID
    sender: str
    body: str | None
    created_at: datetime
    source: str | None


class SupportThreadDetail(BaseModel):
    conversation_id: UUID
    user_id: UUID
    username: str | None
    email: str | None
    messages: list[SupportMessageItem]


class SupportReplyRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)


def _message_item(message: Message, user_id: UUID) -> SupportMessageItem:
    sender = (
        "user"
        if message.sender_id == user_id
        else "system"
        if message.kind == "system"
        else "support"
    )
    source = message.payload.get("source")
    return SupportMessageItem(
        id=message.id,
        sender=sender,
        body=message.body,
        created_at=message.created_at,
        source=source if isinstance(source, str) else None,
    )


async def _detail(session: AsyncSession, conversation_id: UUID) -> SupportThreadDetail:
    user, messages = await admin_support_service.get_thread(session, conversation_id)
    return SupportThreadDetail(
        conversation_id=conversation_id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        messages=[_message_item(message, user.id) for message in messages],
    )


@router.get("", response_model=list[SupportThreadItem])
async def list_support_threads(
    _admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> list[SupportThreadItem]:
    rows = await admin_support_service.list_threads(session)
    return [SupportThreadItem(**row.__dict__) for row in rows]


@router.get("/{conversation_id}", response_model=SupportThreadDetail)
async def get_support_thread(
    conversation_id: UUID,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> SupportThreadDetail:
    return await _detail(session, conversation_id)


@router.post("/{conversation_id}/reply", response_model=SupportThreadDetail)
async def reply_to_support_thread(
    conversation_id: UUID,
    body: SupportReplyRequest,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> SupportThreadDetail:
    user, _ = await admin_support_service.append_reply(
        session,
        conversation_id,
        body.body,
        sender_id=None,
        payload={"source": "admin", "admin_id": str(admin.id)},
    )
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="support.reply",
        target=str(conversation_id),
        detail={"user_id": str(user.id)},
    )
    await session.commit()
    await email_service.send_to_user(
        session,
        user.id,
        subject="Dueloro Support replied",
        body=body.body.strip(),
        link_path="/social?tab=inbox",
        reply_to=reply_address(conversation_id),
    )
    return await _detail(session, conversation_id)
