"""Social aggregates — friendships and challenges."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

FRIENDSHIP_STATES = ("pending", "accepted", "blocked")
CHALLENGE_STATES = ("sent", "accepted", "declined", "expired")


class Friendship(Base, TimestampMixin):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friendships_pair"),
        CheckConstraint("user_id <> friend_id", name="ck_friendships_no_self"),
        CheckConstraint(
            "state IN ('pending', 'accepted', 'blocked')",
            name="ck_friendships_state",
        ),
    )

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    friend_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", nullable=False
    )
    blocked_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Challenge(Base, TimestampMixin):
    __tablename__ = "challenges"
    __table_args__ = (
        CheckConstraint(
            "state IN ('sent', 'accepted', 'declined', 'expired')",
            name="ck_challenges_state",
        ),
        CheckConstraint("entry_cents > 0", name="ck_challenges_entry_pos"),
        CheckConstraint(
            "(challengee_id IS NOT NULL) OR (invite_token IS NOT NULL)",
            name="ck_challenges_recipient",
        ),
        Index("ix_challenges_created_at", "created_at"),
    )

    id = uuid_pk()
    challenger_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    challengee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    invite_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    speed: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # True ⇒ accepting forms a zero-rake friendly (pair past the rake-bearing cap).
    friendly: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(16), default="sent", server_default="sent", nullable=False
    )
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rematch_of: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
