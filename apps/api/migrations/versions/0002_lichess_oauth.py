"""Pending Lichess OAuth (PKCE) attempts for ownership-verified linking.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lichess_oauth_states",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        op.f("ix_lichess_oauth_states_expires_at"),
        "lichess_oauth_states",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lichess_oauth_states_user_id"),
        "lichess_oauth_states",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_lichess_oauth_states_user_id"), table_name="lichess_oauth_states"
    )
    op.drop_index(
        op.f("ix_lichess_oauth_states_expires_at"), table_name="lichess_oauth_states"
    )
    op.drop_table("lichess_oauth_states")
