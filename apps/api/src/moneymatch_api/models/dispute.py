"""Contest dispute — a participant contests how a settled contest was graded.

The user-facing trust valve for the settlement engine: when a result looks
wrong (host outage, disconnect, ambiguous tie), the player files a dispute that
an admin reviews. One dispute per (match, user); resolution is admin-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

DISPUTE_STATUSES = ("open", "resolved", "rejected")


class Dispute(Base, TimestampMixin):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'rejected')", name="ck_disputes_status"
        ),
        # A user contests a given contest at most once.
        Index("uq_disputes_match_user", "match_id", "user_id", unique=True),
    )

    id = uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open", nullable=False
    )
    # Admin's resolution note (shown back to the user once resolved/rejected).
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
