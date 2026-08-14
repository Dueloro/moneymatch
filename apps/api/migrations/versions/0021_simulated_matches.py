"""simulated_matches — injected results for demoing settlement

Demo scaffolding (IMPLEMENTATION_PROMPT phase 0). A row is a finished match that
never happened, shaped so the grading path reads it exactly as it reads a real
one. Inert unless `DEMO_SIMULATE_ENABLED` is set; see
`models/demo_simulation.py` for why it has to be a table rather than a fake in
one process.

Revision ID: 0021_simulated_matches
Revises: 0020_seed_pubg_flag
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_simulated_matches"
down_revision: str | None = "0020_seed_pubg_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulated_matches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("drawn", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("moves", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rounds", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_simulated_matches_user_id", "simulated_matches", ["user_id"])
    op.create_index(
        "ix_simulated_matches_lookup",
        "simulated_matches",
        ["game", "host_account_id", "created_at_ms"],
    )


def downgrade() -> None:
    op.drop_index("ix_simulated_matches_lookup", table_name="simulated_matches")
    op.drop_index("ix_simulated_matches_user_id", table_name="simulated_matches")
    op.drop_table("simulated_matches")
