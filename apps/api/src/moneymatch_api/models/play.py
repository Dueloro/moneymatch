"""Head-to-head play aggregates (01-architecture §2 · Play).

Three tables move the PoC's in-memory `match_queue.py` onto Postgres so queue
state survives a restart and pairing is race-safe under `FOR UPDATE SKIP LOCKED`
(migration-map §4.6):

- `queue_tickets` — a player waiting to be paired. Escrow is **not** taken while
  waiting (escrow happens at match confirm); a ticket past `expires_at` is
  expired by the worker. `baseline_snapshot` freezes the metric-model values used
  for pairing so a later refresh can't alter an in-flight decision.
- `matches` — a paired contest with its frozen economics (`entry`/`pot`/`prize`/
  `rake`, all integer cents; `rake_bps` not a float `rake_pct`). `outcome_detail`
  + `engine_version` + `raw_payload_id` make every settlement replayable from
  stored inputs (audit requirement).
- `match_players` — the two seats, each with a frozen `baseline_snapshot`, the
  brokered `play_url`/`color`, the graded `stat_line`, and its `payout_cents`.

State machines are explicit and live in `services/match_states.py`; money only
moves through `wallet_service` inside the transition's transaction.
"""

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

# Queue products. Only `duel` is exercised in Phase 3; pool/tournament reuse the
# same ticket table in Phase 4 (the extra nullable columns reserve their shape).
QUEUE_PRODUCTS = ("duel", "pool", "tournament")

# Ticket lifecycle (lowercase — architecture §2). A ticket is `waiting` until it
# pairs (`matched`), is withdrawn (`canceled`), or ages out (`expired`).
TICKET_STATES = ("waiting", "matched", "canceled", "expired")

# Match lifecycle (uppercase — architecture §2). Terminal: SETTLED/PUSHED/CANCELED.
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
        # Pairing scans compatible candidates by (game, market, tier, state).
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
    # Chess time control; null for CS2/Dota.
    speed: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Pools only (Phase 4); reserved here.
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Rating used for the chess Elo band (null for stat duels).
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Frozen metric-model values used for pairing (μ/σ/n per metric + rating).
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    # Pools only (Phase 4).
    personal_bar: Mapped[float | None] = mapped_column(nullable=True)
    # Widening-ladder stage the ticket has reached (0-based); drives the band `w`.
    tolerance_stage: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(16), default="waiting", server_default="waiting", nullable=False
    )
    # The contest this ticket formed into (exactly one is set when state →
    # matched, keyed by `product`): an H2H match, a solo pool, or a tournament.
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
    # Rake as basis points (integer) — never a float `rake_pct` (00-README §3.3).
    rake_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    pot_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prize_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rake_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16),
        default="PENDING",
        server_default="PENDING",
        nullable=False,
        index=True,  # worker scans due matches by state → ix_matches_state
    )
    # True ⇒ the platform brokered the game (chess open challenge); the graded
    # host game id lands in `host_game_id`.
    brokered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # True ⇒ a zero-rake friendly (a friend challenge past the pair rake-cap):
    # both entries are refunded on settle and it's excluded from the leaderboard.
    # The winner is still graded/recorded; only the money flow is neutralized
    # (08-phase-5 · collusion posture for friends). rake_bps is 0 for these.
    friendly: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    host_game_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Server-owned "play your next match after this" anchor — never client-set.
    matched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Current deadline for the current state (confirm deadline while PENDING;
    # resolution deadline once ACTIVE). Extended by host downtime, ceiling in code.
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
    # The host response the grading decision was computed from (audit back-ref).
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
    # The host account id bound to this seat (the settlement poll / verify key).
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Chess color (white/black); null for coordinated CS2/Dota.
    color: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Brokered game link shown on "Go play" (chess); null otherwise.
    play_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Rating frozen at pairing (chess band + display).
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Metric-model values frozen at pairing (audit + dispute replay).
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payout_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    # Graded stat line for the Activity UI (stat-race markets).
    stat_line: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
