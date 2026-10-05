"""bucket_disputes — dispute lifecycle for bucketing contests (Phase 6)

A participant contests how a bucket contest graded. Opening a dispute snapshots
the relevant settlement + audit evidence (so later recomputes can't alter it) and
may place a hold that blocks the payout/withdrawal until an admin resolves it.

Lifecycle: open → under_review → (resolved_no_change | resolved_refund |
resolved_adjust). Every transition is also written to `audit_events` by the
service, so the trail can't be quietly edited.

Revision ID: 0031_bucket_disputes
Revises: 0030_ledger_bucket_ref_type
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_bucket_disputes"
down_revision: str | None = "0030_ledger_bucket_ref_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = (
    "open",
    "under_review",
    "resolved_no_change",
    "resolved_refund",
    "resolved_adjust",
)


def upgrade() -> None:
    op.create_table(
        "bucket_dispute",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bucket_contest.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="'open'"),
        # Immutable evidence snapshot taken at open time.
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("hold", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("admin_note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open','under_review','resolved_no_change',"
            "'resolved_refund','resolved_adjust')",
            name="ck_bucket_dispute_status",
        ),
    )
    op.create_index(
        "ix_bucket_dispute_contest", "bucket_dispute", ["contest_id"]
    )
    # One dispute per (contest, user).
    op.create_index(
        "uq_bucket_dispute_contest_user",
        "bucket_dispute",
        ["contest_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("bucket_dispute")
