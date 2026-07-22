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

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

LINK_METHODS = ("username", "oauth")
# `unbound` is a soft-unbind (admin action): the row is retained so its contest
# history (match_players / queue_tickets FKs) stays intact, but it releases the
# uniqueness slots (the unique indexes are partial on `status <> 'unbound'`) so
# the host account can be rebound to a fresh row (backlog · soft-unbind).
LINKED_ACCOUNT_STATUSES = ("active", "frozen", "unbound")

# Only a live (non-unbound) binding holds the slot, so an account that has *played*
# can be soft-unbound and re-linked without a hard delete (which FK RESTRICT
# forbids). Names match the pre-existing constraints so `bind()`'s IntegrityError
# mapping is unchanged.
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
