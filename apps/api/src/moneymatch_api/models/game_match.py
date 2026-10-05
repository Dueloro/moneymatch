"""Stored per-player match history — what every tournament now scores from.

One row per (player's host account, host match): the background ingester
(`services/match_ingestion.py`) fetches each linked account's finished games on
a schedule and writes them here. Contests read this table instead of calling a
game's API at settlement time, which is what keeps PUBG inside its rate limit
and makes a result reproducible from our own data.

Every game the host reports is stored, eligible or not (a PUBG custom match, a
casual chess game), so the history is complete for later skill grouping; the
`eligible` / `rated` flags say whether it can count toward a contest.

**Append-only.** Rows are inserted with ON CONFLICT DO NOTHING (ingestion is
idempotent: the same match fetched twice is one row) and a trigger rejects
UPDATE/DELETE, so a stored result cannot be edited after the fact.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk

#: The player's result in the match, from their side.
GAME_RESULTS = ("win", "loss", "draw")


class GameMatch(Base):
    __tablename__ = "game_matches"
    __table_args__ = (
        # The idempotency key: one host match per host account, ever.
        UniqueConstraint(
            "game",
            "host_account_id",
            "host_match_id",
            name="uq_game_matches_account_match",
        ),
        # Tournament scoring and the admin log read one account's games by time.
        Index(
            "ix_game_matches_account_started", "game", "host_account_id", "started_at"
        ),
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
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    host_match_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Host timestamps. `ended_at` is null when the host does not report it.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Chess time control, PUBG game mode, etc.
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # False ⇒ the host reported it but it can never count (custom/event modes).
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # "win" | "loss" | "draw" | null (unknown).
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Full moves (chess); 0 elsewhere.
    moves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Per-match rate stats, keyed like `metric_models` (e.g. "pubg_kills").
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    # Host-specific facts (opponent + rating for chess, placement for PUBG).
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )
