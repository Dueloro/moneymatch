"""Risk flags — the sandbagging trail (07-phase-4 · deliverable 10).

Tanking a baseline is the attack the personal-bar feature invites (a low frozen
μ makes your bar trivially clearable), so the sandbagging detector ships *with*
it. When a player's recent-form mean drops markedly below their lifetime mean
(z below a threshold), we write a `risk_flags` row and block metric wagers on
that game/metric until an admin clears it. The admin review queue lands in
Phase 6; this table is the durable signal it will read.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk

RISK_FLAG_KINDS = ("sandbagging",)


class RiskFlag(Base):
    __tablename__ = "risk_flags"
    __table_args__ = (
        CheckConstraint("kind IN ('sandbagging')", name="ck_risk_flags_kind"),
    )

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    # An admin clears it in Phase 6; while false, metric wagers are blocked.
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )
