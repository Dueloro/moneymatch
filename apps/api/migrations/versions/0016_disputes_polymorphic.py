"""disputes → polymorphic (ref_type, ref_id) across match / pool / tournament

Revision ID: 0016_disputes_polymorphic
Revises: 0015_live_snapshots
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_disputes_polymorphic"
down_revision: str | None = "0015_live_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New polymorphic ref columns (nullable while we backfill).
    op.add_column("disputes", sa.Column("ref_type", sa.String(16), nullable=True))
    op.add_column("disputes", sa.Column("ref_id", sa.dialects.postgresql.UUID(), nullable=True))

    # Every existing dispute pointed at a match.
    op.execute("UPDATE disputes SET ref_type = 'match', ref_id = match_id")

    op.alter_column("disputes", "ref_type", nullable=False)
    op.alter_column("disputes", "ref_id", nullable=False)

    # Swap the (match_id, user_id) unique index for the polymorphic one.
    op.drop_index("uq_disputes_match_user", table_name="disputes")
    op.drop_constraint("disputes_match_id_fkey", "disputes", type_="foreignkey")
    op.drop_column("disputes", "match_id")

    op.create_index("ix_disputes_ref_id", "disputes", ["ref_id"])
    op.create_index(
        "uq_disputes_ref_user",
        "disputes",
        ["ref_type", "ref_id", "user_id"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_disputes_ref_type",
        "disputes",
        "ref_type IN ('match', 'pool', 'tournament')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_disputes_ref_type", "disputes", type_="check")
    op.drop_index("uq_disputes_ref_user", table_name="disputes")
    op.drop_index("ix_disputes_ref_id", table_name="disputes")

    op.add_column(
        "disputes", sa.Column("match_id", sa.dialects.postgresql.UUID(), nullable=True)
    )
    # Only match disputes can survive the down-migration's FK.
    op.execute("DELETE FROM disputes WHERE ref_type <> 'match'")
    op.execute("UPDATE disputes SET match_id = ref_id")
    op.alter_column("disputes", "match_id", nullable=False)
    op.create_foreign_key(
        "disputes_match_id_fkey",
        "disputes",
        "matches",
        ["match_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_disputes_match_user", "disputes", ["match_id", "user_id"], unique=True
    )
    op.drop_column("disputes", "ref_id")
    op.drop_column("disputes", "ref_type")
