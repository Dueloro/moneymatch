"""Admin and inbound-email operations for user support threads."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import APIError
from ..models.chat import MAX_MESSAGE_CHARS, Conversation, ConversationMember, Message
from ..models.user import User


@dataclass
class SupportThreadSummary:
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    username: str | None
    email: str | None
    last_message_at: datetime | None
    last_message_preview: str | None
    awaiting_reply: bool


async def _support_user(
    session: AsyncSession, conversation_id: uuid.UUID
) -> tuple[Conversation, User]:
    row = (
        await session.execute(
            select(Conversation, User)
            .join(
                ConversationMember,
                ConversationMember.conversation_id == Conversation.id,
            )
            .join(User, User.id == ConversationMember.user_id)
            .where(
                Conversation.id == conversation_id,
                Conversation.kind == "support",
            )
        )
    ).one_or_none()
    if row is None:
        raise APIError(
            "support_thread_not_found", "No such support thread.", status_code=404
        )
    conversation, user = row
    return conversation, user


async def list_threads(session: AsyncSession) -> list[SupportThreadSummary]:
    rows = list(
        (
            await session.execute(
                select(Conversation, User)
                .join(
                    ConversationMember,
                    ConversationMember.conversation_id == Conversation.id,
                )
                .join(User, User.id == ConversationMember.user_id)
                .where(Conversation.kind == "support")
                .order_by(Conversation.last_message_at.desc().nullslast())
            )
        ).all()
    )
    summaries: list[SupportThreadSummary] = []
    for conversation, user in rows:
        last = await session.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.kind == "text",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        summaries.append(
            SupportThreadSummary(
                conversation_id=conversation.id,
                user_id=user.id,
                username=user.username,
                email=user.email,
                last_message_at=conversation.last_message_at,
                last_message_preview=(last.body[:160] if last and last.body else None),
                awaiting_reply=bool(last and last.sender_id == user.id),
            )
        )
    return summaries


async def get_thread(
    session: AsyncSession, conversation_id: uuid.UUID
) -> tuple[User, list[Message]]:
    _, user = await _support_user(session, conversation_id)
    messages = list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    )
    return user, messages


async def append_reply(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    body: str,
    *,
    sender_id: uuid.UUID | None,
    payload: dict[str, str] | None = None,
) -> tuple[User, Message]:
    conversation, user = await _support_user(session, conversation_id)
    text = body.strip()
    if not text:
        raise APIError("empty_message", "Write something first.", status_code=422)
    if len(text) > MAX_MESSAGE_CHARS:
        raise APIError(
            "message_too_long",
            f"Messages are capped at {MAX_MESSAGE_CHARS} characters.",
            status_code=422,
        )
    message = Message(
        conversation_id=conversation.id,
        sender_id=sender_id,
        kind="text",
        body=text,
        payload=payload or {},
    )
    session.add(message)
    await session.flush()
    conversation.last_message_at = message.created_at
    await session.flush()
    return user, message


async def has_resend_email(session: AsyncSession, email_id: str) -> bool:
    found = await session.scalar(
        select(Message.id)
        .where(Message.payload["resend_email_id"].astext == email_id)
        .limit(1)
    )
    return found is not None
