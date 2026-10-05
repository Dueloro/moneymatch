"""Tournaments wait for a second player before their clock starts.

A tournament opened by one player has no window yet: `window_starts_at` and
`window_ends_at` stay null ("waiting") until a second player joins, which
starts the clock. Relaxing NOT NULL only; no data changes.

Revision ID: 0036_tournament_waiting_phase
Revises: 0035_tournament_settlement_log
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_tournament_waiting_phase"
down_revision: str | None = "0035_tournament_settlement_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for col in ("window_starts_at", "window_ends_at"):
        op.alter_column(
            "tournaments", col, existing_type=sa.DateTime(timezone=True), nullable=True
        )


def downgrade() -> None:
    # A still-waiting tournament has no window; give it one so NOT NULL holds.
    op.execute(
        "UPDATE tournaments SET window_starts_at = created_at "
        "WHERE window_starts_at IS NULL"
    )
    op.execute(
        "UPDATE tournaments SET window_ends_at = created_at "
        "WHERE window_ends_at IS NULL"
    )
    for col in ("window_starts_at", "window_ends_at"):
        op.alter_column(
            "tournaments", col, existing_type=sa.DateTime(timezone=True), nullable=False
        )
