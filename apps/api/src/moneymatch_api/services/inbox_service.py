"""The Social badge: unread DMs and notifications that arrived since the user last
opened Social. Per-item read state (thread cursors, `read_at`) is separate.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.chat import ConversationMember, Message
from ..models.notification import Notification
from ..models.user import User


async def badge(session: AsyncSession, user: User) -> int:
    seen = user.inbox_seen_at
    messages = (
        select(func.count(Message.id))
        .select_from(ConversationMember)
        .join(Message, Message.conversation_id == ConversationMember.conversation_id)
        .where(
            ConversationMember.user_id == user.id,
            or_(Message.sender_id.is_(None), Message.sender_id != user.id),
            or_(
                ConversationMember.last_read_at.is_(None),
                Message.created_at > ConversationMember.last_read_at,
            ),
        )
    )
    notes = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    if seen is not None:
        messages = messages.where(Message.created_at > seen)
        notes = notes.where(Notification.created_at > seen)
    return int(await session.scalar(messages) or 0) + int(
        await session.scalar(notes) or 0
    )


async def mark_seen(session: AsyncSession, user: User) -> None:
    user.inbox_seen_at = await session.scalar(select(func.clock_timestamp()))
    await session.flush()
