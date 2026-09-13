"""ORM model for the win-streak matchmaking ladder (migration 0032)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk


class PlayerStreak(Base):
    """A player's transient consecutive-win streak per (game, mode). Matchmaking
    only — never money."""

    __tablename__ = "player_streak"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "game", "mode", name="uq_player_streak_player_game_mode"
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
    streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    best_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
