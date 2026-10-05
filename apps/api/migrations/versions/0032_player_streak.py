"""player_streak — the transient win-streak that drives the matchmaking ladder

One small mutable row per (player, game, mode): the current consecutive-win
`streak` (lifts the matchmaking target a rung per win, resets to 0 on a loss) and
a `best_streak` for display/analytics. Matchmaking-only — it never touches money
or what a player wagers. Inert until `bucketing_enabled` is on.

Revision ID: 0032_player_streak
Revises: 0031_bucket_disputes
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_player_streak"
down_revision: str | None = "0031_bucket_disputes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_streak",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "player_id", "game", "mode", name="uq_player_streak_player_game_mode"
        ),
    )


def downgrade() -> None:
    op.drop_table("player_streak")
