"""Live-snapshot cache for the Activity feed (in-flight contests).

The settlement worker computes a best-effort "what's happening right now" view
for each in-flight pool and head-to-head match on a slow cadence and upserts it
here; the `/activity` request path only *reads* this table, so no external host
call ever happens while serving a page (same posture as the tournament
`standings_cache`). Tournaments keep their own richer cache and are not stored
here.

`data` is host-shaped, best-effort JSON — never money, never client input.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

# The contest kinds we cache a live view for.
LIVE_REF_TYPES = ("pool", "match")


class LiveSnapshot(Base):
    __tablename__ = "live_snapshots"
    __table_args__ = (
        CheckConstraint(
            "ref_type IN ('pool', 'match')", name="ck_live_snapshots_ref_type"
        ),
    )

    # (ref_type, ref_id) is the natural key — one live view per contest.
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
