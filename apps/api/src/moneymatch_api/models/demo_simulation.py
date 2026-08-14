"""Injected match results, for demoing settlement without waiting on a host.

**Scaffolding. Delete with the rest of the demo surface before launch.**

A live demo of a wager product has to show a contest settling, and settlement
reads real match history from a game host. For CS2 that means a 40-minute FaceIt
match with ten people in it, which is not something you can schedule around an
audience. A row here is a finished match that never happened, written so the
grading path cannot tell the difference.

Why a table rather than a stub in the test suite: the settlement worker is a
separate process from the API, so an in-memory fake in one cannot be seen by the
other. It has to be shared state, and the database is the shared state we have.

Nothing reads this unless `DEMO_SIMULATE_ENABLED` is set. With the flag off,
`adapters.registry.get()` hands back the untouched host adapter and these rows
are inert.
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
    String,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk


class SimulatedMatch(Base):
    """One injected finished match for one linked host account."""

    __tablename__ = "simulated_matches"
    __table_args__ = (
        # The adapter looks these up by host account and window, exactly as it
        # would query a host.
        Index(
            "ix_simulated_matches_lookup",
            "game",
            "host_account_id",
            "created_at_ms",
        ),
    )

    id = uuid_pk()
    # Kept for the audit trail and for the admin view; the read path keys off
    # `host_account_id`, because that is what a host feed is keyed by.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Shaped to fill a `NormGame` with no further translation.
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drawn: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    moves: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    rounds: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # Who injected it and when. A simulated settlement must never be mistaken
    # for a real one after the fact.
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
