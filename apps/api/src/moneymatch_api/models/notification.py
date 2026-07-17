"""Notifications (01-architecture §2 · Social & ops).

Phase 3 **writes** rows (`match_found`, `settled`, `refund`) inside the
transition that causes them; Phase 5's Inbox screen consumes them. Rows are
mutable only in `read_at` (marking read), so no append-only trigger here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk

# Every lifecycle event fans out to one of these (08-phase-5 · deliverable 7).
# Phase 3 wrote match_found/settled/refund; Phase 5 adds the social kinds.
NOTIFICATION_KINDS = (
    "match_found",
    "settled",
    "refund",
    "challenge_received",
    "challenge_accepted",
    "friend_request",
    "room_filled",
    "system",
)

_KIND_SQL = ", ".join(f"'{k}'" for k in NOTIFICATION_KINDS)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_KIND_SQL})",
            name="ck_notifications_kind",
        ),
    )

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Which out-of-band channels have been dispatched (email/push are post-MVP;
    # the schema carries the flag now — 08-phase-5 · deliverable 7).
    channel_sent: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )
