"""Skill & audit substrate (01-architecture §2 · Skill & audit substrate).

- `metric_models` — per `(user_id, game, metric)`, an EWMA `mu`/`sigma` and a
  sample size `n` over the account's recent finished matches (half-life 10).
  Computed at link time, refreshed on settlement (Phase 3) and nightly. `n` below
  a floor makes the metric **provisional** (no stat duels/pools on it). Mutable —
  refreshed in place, so no append-only trigger here.
- `raw_payloads` — every host-API response used in a grading/profile decision,
  kept with a content hash so a derived record can reference its exact proof.
  **Append-only** (immutable audit trail): the shared `mm_reject_mutation`
  trigger rejects UPDATE/DELETE (00-README §3.2).
"""

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
    # A typed rate metric key, e.g. "cs2_kd_ratio", "dota2_gpm".
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    mu: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sigma: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Number of matches that fed the model — below the floor ⇒ provisional.
    n: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class RawPayload(Base):
    """Append-only host-response record (no `updated_at`: rows are immutable)."""

    __tablename__ = "raw_payloads"

    id = uuid_pk()
    # Where it came from, e.g. "lichess:user", "faceit:match_stats".
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # sha256 of the canonical payload bytes — dedupe + tamper-evidence.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Total bytes of the stored payload (a cheap retention/ops signal).
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
