"""Skill & audit substrate."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk


class MetricModel(Base, TimestampMixin):
    __tablename__ = "metric_models"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "game", "metric", name="uq_metric_models_user_game_metric"
        ),
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
    mu: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0", nullable=False
    )
    sigma: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0", nullable=False
    )
    n: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class RawPayload(Base):
    """Append-only host-response record (no `updated_at`: rows are immutable)."""

    __tablename__ = "raw_payloads"

    id = uuid_pk()
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # sha256 of the canonical payload bytes — dedupe + tamper-evidence.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
