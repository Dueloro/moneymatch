"""The permanent record of how a finished tournament was decided.

Written once, when a tournament settles (paid out or refunded), so a dispute
can be answered from our own data long after the live standings are gone:

- `tournament_results`: one row per entrant — their final score, rank, payout
  and outcome, plus who they were at the time (username, host account).
- `tournament_match_log`: one row per (entrant, fetched match) — every game we
  had stored for that player around the tournament, with the verdict the rules
  gave it (counted or why not), the value it contributed, the stats it was
  scored from, and its timestamps: when it started and ended on the host, and
  when *we* fetched it.

**Append-only** (a trigger rejects UPDATE/DELETE), like the ledger and
`game_matches`. Users and entries are referenced by id without foreign keys on
purpose: the record must survive anything that later happens to those rows
(e.g. practice-bot cleanup), and it snapshots the username for that reason.
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk

#: Outcomes recorded per entrant.
RESULT_OUTCOMES = ("paid", "unpaid", "refunded", "unverifiable", "forfeit")


class TournamentResult(Base):
    __tablename__ = "tournament_results"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id", "entry_id", name="uq_tournament_results_entry"
        ),
    )

    id = uuid_pk()
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matches_counted: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payout_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    # The tournament's outcome reason (e.g. "not_enough_players"), if refunded.
    tournament_outcome: Mapped[str | None] = mapped_column(String(48), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )


class TournamentMatchLog(Base):
    __tablename__ = "tournament_match_log"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "entry_id",
            "host_match_id",
            name="uq_tournament_match_log_entry_match",
        ),
    )

    id = uuid_pk()
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    # The stored match this verdict was made on (game_matches is append-only too).
    game_match_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("game_matches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    host_match_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When our ingester fetched the match from the host.
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # The rules' verdict (tournament_scoring reason code) and what it added.
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    counted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The match's stats as stored when the tournament was decided.
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
