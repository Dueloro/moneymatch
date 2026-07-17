"""Linked host-game accounts (01-architecture §2 · Identity).

A `linked_accounts` row binds one host account (Lichess/FaceIt/OpenDota) to one
platform user. Two DB-enforced uniqueness rules make the binding immutable and
non-shareable (05-phase-2 · deliverable 2):

- `(user_id, game)` — a user links at most one account per game;
- `(game, host_account_id)` — a host account binds to at most one user, so a
  second user racing to claim it fails on the constraint, not an app check.

`profile_snapshot` caches the last-fetched `ProfileSnapshot`; `link_method`
reserves the OAuth path (the next step after MVP). `status` freezes a binding
independently of the per-game feature flag; either one renders BLOCKED on Profile.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

LINK_METHODS = ("username", "oauth")
LINKED_ACCOUNT_STATUSES = ("active", "frozen")


class LinkedAccount(Base, TimestampMixin):
    __tablename__ = "linked_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "game", name="uq_linked_accounts_user_game"),
        UniqueConstraint(
            "game", "host_account_id", name="uq_linked_accounts_game_host"
        ),
        CheckConstraint(
            "link_method IN ('username', 'oauth')",
            name="ck_linked_accounts_link_method",
        ),
        CheckConstraint(
            "status IN ('active', 'frozen')", name="ck_linked_accounts_status"
        ),
    )

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Canonical `<game>.<host>` id (constants.REGISTERED_GAMES).
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    # The host's stable account id (the settlement poll key).
    host_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # The host's display handle (what the user typed / sees).
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
