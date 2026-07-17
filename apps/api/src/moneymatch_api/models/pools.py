"""Solo pool aggregates (01-architecture §2 · Play; 07-phase-4).

A **solo pool** is a queue-matched room of similar-stat players who each try to
clear a **personalized bar** (`μ + k·σ` from their own frozen baseline) in their
own next match. Clearers split the pooled entries minus rake; nobody clears →
full refund, zero rake. There is no house — the prize is entrants' money only.

- `solo_pools` — the formed room: its server-derived `room_bar` (the rounded mean
  of members' personal bars, byte-for-byte reproducible from the stored
  baselines), frozen economics (integer cents), and the settlement window.
- `solo_entries` — one seat: the member's frozen `personal_bar` +
  `baseline_snapshot`, the server-fetched `telemetry`, its grading `raw_payload`,
  and its `payout_cents`. No column here is ever set from client input.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

POOL_DIFFICULTIES = ("easy", "medium", "hard")
# OPEN (forming) → LOCKED (window running) → SETTLED | CANCELED (terminal).
POOL_STATES = ("OPEN", "LOCKED", "SETTLED", "CANCELED")
# LOCKED (escrowed) → CLEARED | MISSED | REFUNDED at settlement.
SOLO_ENTRY_STATUSES = ("LOCKED", "CLEARED", "MISSED", "REFUNDED")


class SoloPool(Base, TimestampMixin):
    __tablename__ = "solo_pools"
    __table_args__ = (
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_solo_pools_difficulty"
        ),
        CheckConstraint(
            "state IN ('OPEN', 'LOCKED', 'SETTLED', 'CANCELED')",
            name="ck_solo_pools_state",
        ),
        CheckConstraint("entry_cents > 0", name="ck_solo_pools_entry_pos"),
        # No pot=prize+rake check: refunded entries are neither prize nor rake, so
        # pot (= total entries) = prize+rake+refunds. reconciliation is the enforcer.
    )

    id = uuid_pk()
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    # Server-derived clear threshold = round(mean(members' personal bars)).
    room_bar: Mapped[float] = mapped_column(Float, nullable=False)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rake_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    room_size: Mapped[int] = mapped_column(Integer, nullable=False)
    min_entrants: Mapped[int] = mapped_column(Integer, nullable=False)
    pot_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    prize_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    rake_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(16), default="LOCKED", server_default="LOCKED", nullable=False
    )
    window_starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SoloEntry(Base, TimestampMixin):
    __tablename__ = "solo_entries"
    __table_args__ = (
        UniqueConstraint("pool_id", "user_id", name="uq_solo_entries_pool_user"),
        CheckConstraint(
            "status IN ('LOCKED', 'CLEARED', 'MISSED', 'REFUNDED')",
            name="ck_solo_entries_status",
        ),
    )

    id = uuid_pk()
    pool_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("solo_pools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    linked_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("linked_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # The member's own bar (μ + k·σ), frozen at enqueue.
    personal_bar: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="LOCKED", server_default="LOCKED", nullable=False
    )
    # Server-fetched grading telemetry (the qualifying match's stat).
    telemetry: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_payload_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_payloads.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payout_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
