"""live_snapshots — cached in-flight view for the Activity feed

Revision ID: 0015_live_snapshots
Revises: 0014_push_subscriptions
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0015_live_snapshots"
down_revision: str | None = "0014_push_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_snapshots",
        sa.Column("ref_type", sa.String(16), primary_key=True),
        sa.Column("ref_id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "data", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ref_type IN ('pool', 'match')", name="ck_live_snapshots_ref_type"
        ),
    )


def downgrade() -> None:
    op.drop_table("live_snapshots")
