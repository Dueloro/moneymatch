"""ORM models for the bucketing layer (migration 0028).

These map the tables the bucketing services read/write. `match_stats` is a
partitioned, append-only table — the ORM doesn't model the partitioning (Postgres
handles routing), but its composite primary key `(id, created_at_ms)` is declared
so inserts carry the partition key. `market_reference` and `settlement` also use
composite keys, matching the migration exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class MatchStat(Base):
    """Append-only raw event log — one row per finished gradable match per player,
    every field the adapter saw in `metrics`. Partitioned monthly by
    `created_at_ms`; the idempotency key includes the partition column."""

    __tablename__ = "match_stats"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "game",
            "host_match_id",
            "created_at_ms",
            name="uq_match_stats_idem",
        ),
    )

    # Composite PK (id, created_at_ms) — the partition key must be in the PK.
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    created_at_ms: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    player_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    host_match_id: Mapped[str] = mapped_column(String(128), nullable=False)
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarketState(Base, TimestampMixin):
    """Derived, mutable per-(player, game, mode, metric) state."""

    __tablename__ = "market_state"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "game", "mode", "metric", name="uq_market_state_player_market"
        ),
    )

    id = uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)

    mean: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    m2: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    window: Mapped[list[float]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    index_value: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    index_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    peak_goodness: Mapped[float | None] = mapped_column(Float, nullable=True)

    bucket: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bucket_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placed_from: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provisional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class MarketReference(Base):
    """Versioned, seasoned cut points + one bar per bucket. A partial unique index
    (in the migration) enforces exactly one `active` row per market."""

    __tablename__ = "market_reference"

    game: Mapped[str] = mapped_column(String(32), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), primary_key=True)
    metric: Mapped[str] = mapped_column(String(48), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    version: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")

    cuts: Mapped[list[float]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    bars: Mapped[list[float]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    k: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    lower_is_better: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="'public'"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Settlement(Base):
    """Append-only audit row: exactly which bucket/bar/version graded a contest."""

    __tablename__ = "settlement"

    contest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    player_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    bucket: Mapped[int] = mapped_column(Integer, nullable=False)
    bar: Mapped[float] = mapped_column(Float, nullable=False)
    reference_season: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_version: Mapped[int] = mapped_column(Integer, nullable=False)
    result_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cleared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    stake_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payout_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    rake_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    refunded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    """Append-only log of anything that touched money or placement (Phase 6)."""

    __tablename__ = "audit_events"

    id = uuid_pk()
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    market: Mapped[str | None] = mapped_column(String(112), nullable=True)
    contest_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="'system'"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
