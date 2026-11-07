"""Live-snapshot cache for the Activity feed (in-flight contests)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

LIVE_REF_TYPES = ("pool", "match")


class LiveSnapshot(Base):
    __tablename__ = "live_snapshots"
    __table_args__ = (
        CheckConstraint(
            "ref_type IN ('pool', 'match')", name="ck_live_snapshots_ref_type"
        ),
    )

    ref_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    ref_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
