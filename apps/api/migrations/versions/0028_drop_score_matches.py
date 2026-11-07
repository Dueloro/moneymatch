"""Drop tournaments.score_matches.

Revision ID: 0028_drop_score_matches
Revises: 0027_dismissed_checklists
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_drop_score_matches"
down_revision: str | None = "0027_dismissed_checklists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tournaments", "score_matches")


def downgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("score_matches", sa.Integer(), server_default="3", nullable=False),
    )
