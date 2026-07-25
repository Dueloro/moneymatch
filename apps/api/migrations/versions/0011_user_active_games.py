"""users.active_games (the player's chosen play set)

Adds a JSONB list of catalog game ids the player has chosen to play. Drives the
games switcher and is decoupled from linking, so a game can be selected (and
shown) before its account is linked. Empty (`[]`) means "not chosen yet"; the
client falls back to every registered game, so existing rows keep their current
switcher without a backfill.

Revision ID: 0011_user_active_games
Revises: 0010_soft_unbind
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011_user_active_games"
down_revision: str | None = "0010_soft_unbind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "active_games",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "active_games")
