"""Linked host-game accounts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

LINK_METHODS = ("username", "oauth")
LINKED_ACCOUNT_STATUSES = ("active", "frozen", "unbound")

_ACTIVE_BINDING = text("status <> 'unbound'")


class LinkedAccount(Base, TimestampMixin):
    __tablename__ = "linked_accounts"
    __table_args__ = (
        Index(
            "uq_linked_accounts_user_game",
            "user_id",
            "game",
            unique=True,
            postgresql_where=_ACTIVE_BINDING,
        ),
        Index(
            "uq_linked_accounts_game_host",
            "game",
            "host_account_id",
            unique=True,
            postgresql_where=_ACTIVE_BINDING,
        ),
        CheckConstraint(
            "link_method IN ('username', 'oauth')",
            name="ck_linked_accounts_link_method",
        ),
        CheckConstraint(
            "status IN ('active', 'frozen', 'unbound')",
            name="ck_linked_accounts_status",
        ),
    )

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    host_username: Mapped[str] = mapped_column(String(128), nullable=False)
    link_method: Mapped[str] = mapped_column(
        String(16), default="username", server_default="username", nullable=False
    )
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )
