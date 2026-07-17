"""Tournament aggregates (01-architecture §2 · Play; 07-phase-4).

A **tournament** is a matchmade single-metric field (~10 similar-stat players
formed under a μ-dispersion cap): everyone plays their normal matches during the
window, the server records the **mean of the metric over the first N qualifying
matches**, and the top 3 split `pot − rake` per a declared `prize_split`
(50/30/20). Ties split combined slices with remainder cents to the earlier
enqueue; zero-match entrants rank below all who played; too few ranked → cancel
+ refund. No house, no odds — the prize is entrants' pooled entries only.

`prize_split` is stored as integer relative **weights** (e.g. `[50, 30, 20]`);
the settlement math normalizes them, so no float split factor is ever persisted.
`standings_cache` holds the live, server-computed standings refreshed on a slow
cadence during the window (cheap reads for the standings panel).
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

TOURNAMENT_STATES = ("OPEN", "LOCKED", "SETTLED", "CANCELED")
# LOCKED (escrowed) → RANKED | OUT | REFUNDED at settlement.
TOURNAMENT_ENTRY_STATUSES = ("LOCKED", "RANKED", "OUT", "REFUNDED")


class Tournament(Base, TimestampMixin):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint(
            "state IN ('OPEN', 'LOCKED', 'SETTLED', 'CANCELED')",
            name="ck_tournaments_state",
        ),
        CheckConstraint("entry_cents > 0", name="ck_tournaments_entry_pos"),
        # No pot=prize+rake check (see solo_pools): refunds live outside prize+rake.
    )

    id = uuid_pk()
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    ranking_metric: Mapped[str] = mapped_column(String(48), nullable=False)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rake_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    # Integer relative weights, e.g. [50, 30, 20]. Normalized at settlement.
    prize_split: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    field_size: Mapped[int] = mapped_column(Integer, nullable=False)
    min_field: Mapped[int] = mapped_column(Integer, nullable=False)
    # Fewer than this many entrants producing a score → CANCELED + refund.
    min_ranked: Mapped[int] = mapped_column(Integer, nullable=False)
    score_matches: Mapped[int] = mapped_column(Integer, nullable=False)  # first-N
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
    # Cheap live standings for the panel (server-computed; refreshed on a cadence).
    standings_cache: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    standings_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TournamentEntry(Base, TimestampMixin):
    __tablename__ = "tournament_entries"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "user_id", name="uq_tournament_entries_tournament_user"
        ),
        CheckConstraint(
            "status IN ('LOCKED', 'RANKED', 'OUT', 'REFUNDED')",
            name="ck_tournament_entries_status",
        ),
    )

    id = uuid_pk()
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
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
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    # Deterministic tie-break: earlier enqueue wins the remainder cent.
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # First-N-average of the ranking metric; null until scored / if no matches.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matches_counted: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="LOCKED", server_default="LOCKED", nullable=False
    )
    telemetry: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_payload_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_payloads.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payout_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
