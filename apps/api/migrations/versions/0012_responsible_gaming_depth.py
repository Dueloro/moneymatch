"""limits: daily deposit cap + self-imposed cool-off (responsible gaming)

Adds `limits.daily_deposit_cap_cents` (a trailing-24h deposit cap, defaulted from
caps.py) and `limits.timeout_until` (a self-imposed cool-off — staking is refused
until it passes; can be extended, never shortened).

Revision ID: 0012_responsible_gaming_depth
Revises: 0011_user_active_games
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from moneymatch_api.caps import CAPS

revision: str = "0012_responsible_gaming_depth"
down_revision: str | None = "0011_user_active_games"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "limits",
        sa.Column(
            "daily_deposit_cap_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=str(CAPS.daily_deposit_cap_cents),
        ),
    )
    op.add_column(
        "limits",
        sa.Column("timeout_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("limits", "timeout_until")
    op.drop_column("limits", "daily_deposit_cap_cents")
