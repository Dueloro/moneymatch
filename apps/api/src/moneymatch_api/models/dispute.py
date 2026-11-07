"""Contest dispute — a participant contests how a settled contest was graded."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

DISPUTE_STATUSES = ("open", "resolved", "rejected")
DISPUTE_REF_TYPES = ("match", "pool", "tournament")


class Dispute(Base, TimestampMixin):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'rejected')", name="ck_disputes_status"
        ),
        CheckConstraint(
            "ref_type IN ('match', 'pool', 'tournament')",
            name="ck_disputes_ref_type",
        ),
        Index("uq_disputes_ref_user", "ref_type", "ref_id", "user_id", unique=True),
    )

    id = uuid_pk()
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
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
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
