"""Resolved CS2 matches — the scoreboard a wager settles on.

A share code is the only artifact a player can copy out of CS2. Resolving one
through the Game Coordinator yields the final scoreboard: per-player kills,
deaths, assists, headshots and MVPs, plus the team scores. That is enough to
grade K/D, headshot-percentage and kill wagers with no demo download and no
parser.

Why the scoreboard is *stored* rather than fetched at settlement time:

- The GC is a stateful, rate-limited Steam service reached through a sidecar.
  If settlement depended on it being up, every wager would be hostage to it.
  Resolve once, store, and grade from the stored row forever.
- `share_code` is **globally unique**. Without that constraint one good match
  could be pasted into ten different wagers. The database is the only place
  that check cannot be raced.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk


class Cs2Match(Base):
    """One resolved CS2 matchmaking match, keyed by its share code."""

    __tablename__ = "cs2_matches"
    __table_args__ = (Index("ix_cs2_matches_match_time", "match_time"),)

    id = uuid_pk()

    # The uniqueness that stops one match settling many wagers. Unique across
    # the whole table, not per user: two players in the same match submitting
    # the same code is the same match, and it should resolve to one row.
    share_code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # Decoded from the share code.
    match_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # From the Game Coordinator.
    match_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    map_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rounds_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    score_a: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    score_b: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    #: One entry per player: steamid plus their scoreboard line. The roster
    #: check at settlement reads this, so it is the security-relevant field.
    players: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )

    #: Valve keeps demos about a month. Absent is normal and does not block
    #: settlement, because the scoreboard is already here; only ADR and the
    #: other parse-only metrics are lost with it.
    demo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    demo_expired: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    #: Who first submitted the code, for the audit trail. Not an ownership
    #: claim: the roster is what ties a match to a player.
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def steam_ids(self) -> set[str]:
        return {str(p.get("steamid")) for p in (self.players or []) if p.get("steamid")}

    def line_for(self, steam_id: str) -> dict[str, Any] | None:
        for player in self.players or []:
            if str(player.get("steamid")) == str(steam_id):
                return player
        return None


class Cs2ShareChain(Base):
    """A player's place in Valve's share-code chain, so codes arrive on their own.

    Valve stores a player's matches as a linked list: given one share code they
    own, `GetNextMatchSharingCode` returns the next. Keeping the cursor here is
    what turns a one-time setup into every future match arriving without a
    paste.

    `auth_code` is a per-user secret issued by Steam. It is not a password and
    cannot spend anything, but it does read someone's match history, so it is
    never logged and never returned by the API — the chain endpoints report
    whether a chain is connected, not what it was connected with.

    One row per user: a second cursor for the same account would race the first
    and double-ingest every match.
    """

    __tablename__ = "cs2_share_chains"

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    steam_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    auth_code: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The most recent code known to be this player's. Advances every poll.
    known_code: Mapped[str] = mapped_column(String(40), nullable=False)
    #: `active`, or `broken` when Valve rejected the cursor or the auth code.
    #: A broken chain stops polling until the player reconnects it, because
    #: repeated bad auth codes get the whole API key temporarily blocked.
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        # Declared on both sides: the Python default covers ORM inserts, the
        # server default covers anything that writes without the model. Only
        # one of them and `alembic check` reports drift on every run.
        server_default=text("'active'"),
    )
    #: Why it broke, in words the player can act on.
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: When this chain last produced a new match, for spotting a silent stall.
    last_code_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def is_active(self) -> bool:
        return self.state == "active"
