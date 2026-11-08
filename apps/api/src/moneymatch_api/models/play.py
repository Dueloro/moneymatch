"""Head-to-head play aggregates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

QUEUE_PRODUCTS = ("duel", "pool", "tournament")

TICKET_STATES = ("waiting", "matched", "canceled", "expired")

MATCH_STATES = (
    "PENDING",
    "ACTIVE",
    "AWAITING_RESULT",
    "SETTLED",
    "PUSHED",
    "CANCELED",
)


class QueueTicket(Base, TimestampMixin):
    __tablename__ = "queue_tickets"
    __table_args__ = (
        CheckConstraint(
            "product IN ('duel', 'pool', 'tournament')",
            name="ck_queue_tickets_product",
        ),
        CheckConstraint(
            "state IN ('waiting', 'matched', 'canceled', 'expired')",
            name="ck_queue_tickets_state",
        ),
        CheckConstraint("entry_cents > 0", name="ck_queue_tickets_entry_pos"),
        Index("ix_queue_tickets_candidates", "game", "market", "entry_cents", "state"),
    )

    id = uuid_pk()
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
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(
        String(16), default="duel", server_default="duel", nullable=False
    )
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    speed: Mapped[str | None] = mapped_column(String(16), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    personal_bar: Mapped[float | None] = mapped_column(nullable=True)
    state: Mapped[str] = mapped_column(
        String(16), default="waiting", server_default="waiting", nullable=False
    )
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    pool_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Match(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING', 'ACTIVE', 'AWAITING_RESULT', "
            "'SETTLED', 'PUSHED', 'CANCELED')",
            name="ck_matches_state",
        ),
        CheckConstraint("entry_cents > 0", name="ck_matches_entry_pos"),
        CheckConstraint(
            "pot_cents = prize_cents + rake_cents", name="ck_matches_econ_reconciles"
        ),
    )

    id = uuid_pk()
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    speed: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Rake as basis points (integer) — never a float `rake_pct`.
    rake_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    pot_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prize_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rake_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16),
        default="PENDING",
        server_default="PENDING",
        nullable=False,
        index=True,
    )
    # True ⇒ a zero-rake friendly (a friend challenge past the pair rake-cap): both
    # entries are refunded on settle and it's excluded from the leaderboard.
    friendly: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    host_game_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    winner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    outcome_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Which grading rules produced the result (disputes replay the exact version).
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_payload_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_payloads.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MatchPlayer(Base, TimestampMixin):
    __tablename__ = "match_players"
    __table_args__ = (
        UniqueConstraint("match_id", "user_id", name="uq_match_players_match_user"),
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
    linked_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("linked_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str | None] = mapped_column(String(8), nullable=True)
    play_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pairing inputs frozen at match time (audit + dispute replay).
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payout_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    stat_line: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
