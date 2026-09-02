"""ORM models for the bucketing wager path (migration 0029)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, uuid_pk


class BucketRoom(Base):
    """A formed room of same-bucket wagers settling against one bar."""

    __tablename__ = "bucket_room"

    id = uuid_pk()
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    bucket: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_season: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_version: Mapped[int] = mapped_column(Integer, nullable=False)
    bar: Mapped[float] = mapped_column(Float, nullable=False)
    lower_is_better: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="'open'"
    )
    pot_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    rake_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BucketContest(Base):
    """One player's wager entry, walking queued → matched → awaiting → settled."""

    __tablename__ = "bucket_contest"

    id = uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    bucket: Mapped[int] = mapped_column(Integer, nullable=False)
    stake_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="'queued'"
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bucket_room.id", ondelete="SET NULL"),
        nullable=True,
    )
    reference_season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bar: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualifying_match_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cleared: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payout_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    matched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
