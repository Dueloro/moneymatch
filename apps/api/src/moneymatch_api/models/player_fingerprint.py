"""ORM model for identity fingerprints (migration 0033)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk


class PlayerFingerprint(Base):
    """One identity signal (device/IP/payment) a player has presented."""

    __tablename__ = "player_fingerprint"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "signal", name="uq_player_fingerprint_player_signal"
        ),
    )

    id = uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal: Mapped[str] = mapped_column(String(160), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
