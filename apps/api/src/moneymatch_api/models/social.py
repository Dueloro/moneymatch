"""Social aggregates — friendships and challenges (01-architecture §2 · Social).

Two tables back the Phase 5 liquidity layer:

- `friendships` — one row per relationship, `user_id` = requester, `friend_id` =
  addressee, `state` in `pending|accepted|blocked`. The `(user_id, friend_id)`
  pair is unique and self-add is rejected by a check; the service also guards the
  reverse pair so A→B and B→A never coexist.
- `challenges` — a direct friend challenge or a link invite. `challengee_id` is
  null for link invites (the `invite_token` carries the recipient instead). On
  accept the challenge forms a PENDING `match` through the same lifecycle service
  and stores its id. `friendly` marks a challenge that will form a zero-rake
  friendly because the pair is past its rake-bearing cap (08-phase-5 · deliverable 3).

Neither table is append-only: friendships transition (pending→accepted), and a
challenge resolves in place (sent→accepted/declined/expired).
"""

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
    # The requester (who sent the request); `friend_id` is the addressee.
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
    # Who blocked, when `state = blocked` (either party may block).
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
        # A direct challenge has a challengee; a link invite has a token. Exactly
        # one of the two identifies the recipient.
        CheckConstraint(
            "(challengee_id IS NOT NULL) OR (invite_token IS NOT NULL)",
            name="ck_challenges_recipient",
        ),
        # Inbox / history ordering scans by recency.
        Index("ix_challenges_created_at", "created_at"),
    )

    id = uuid_pk()
    challenger_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Null for link invites (the token carries the recipient).
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
    # The PENDING match created on accept (null until then).
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # The settled match this challenge rematches, if any (rematch button).
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
