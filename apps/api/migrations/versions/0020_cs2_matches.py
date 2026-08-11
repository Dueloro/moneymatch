"""cs2_matches — resolved CS2 scoreboards, keyed by share code

A share code resolves to the final scoreboard through the Game Coordinator.
Storing it means settlement never depends on the GC being reachable, and the
unique constraint on `share_code` is what stops one good match settling many
wagers. That check cannot be raced anywhere but the database.

Revision ID: 0020_cs2_matches
Revises: 0019_simulated_matches
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_cs2_matches"
down_revision: str | None = "0019_simulated_matches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cs2_matches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("share_code", sa.String(64), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("outcome_id", sa.BigInteger(), nullable=False),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("match_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("map_name", sa.String(64), nullable=True),
        sa.Column("rounds_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "players",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("demo_url", sa.String(512), nullable=True),
        sa.Column(
            "demo_expired", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "submitted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # Unique index rather than a unique constraint: this is the check that
    # stops one match settling many wagers, and it must match how the model
    # declares it or every alembic check reports drift.
    op.create_index(
        "ix_cs2_matches_share_code", "cs2_matches", ["share_code"], unique=True
    )
    op.create_index("ix_cs2_matches_match_time", "cs2_matches", ["match_time"])


def downgrade() -> None:
    op.drop_index("ix_cs2_matches_match_time", table_name="cs2_matches")
    op.drop_index("ix_cs2_matches_share_code", table_name="cs2_matches")
    op.drop_table("cs2_matches")
