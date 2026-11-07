"""Three tables back the Inbox's messaging surface: Messages are immutable in `body`
but an `invite` row's `payload.status` flips once (pending → accepted/declined),
so this is not an append-only table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

CONVERSATION_KINDS = ("dm", "support")
MESSAGE_KINDS = ("text", "invite", "system")
INVITE_KINDS = ("pool", "tournament", "h2h")
INVITE_STATUSES = ("pending", "accepted", "declined", "expired")

_CONVERSATION_KIND_SQL = ", ".join(f"'{k}'" for k in CONVERSATION_KINDS)
_MESSAGE_KIND_SQL = ", ".join(f"'{k}'" for k in MESSAGE_KINDS)

MAX_MESSAGE_CHARS = 2000


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_CONVERSATION_KIND_SQL})", name="ck_conversations_kind"
        ),
        Index("ix_conversations_last_message_at", "last_message_at"),
    )

    id = uuid_pk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ConversationMember(Base, TimestampMixin):
    __tablename__ = "conversation_members"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "user_id", name="uq_conversation_members_pair"
        ),
    )

    id = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_MESSAGE_KIND_SQL})", name="ck_messages_kind"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(16), default="text", server_default="text", nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )
