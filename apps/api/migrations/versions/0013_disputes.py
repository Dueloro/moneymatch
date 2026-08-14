"""disputes — user-filed contest disputes

A participant contests how a settled contest was graded; an admin resolves it.
One dispute per (match, user).

Revision ID: 0013_disputes
Revises: 0012_responsible_gaming_depth
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0013_disputes"
down_revision: str | None = "0012_responsible_gaming_depth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "disputes",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "match_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("matches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'rejected')", name="ck_disputes_status"
        ),
    )
    op.create_index("ix_disputes_match_id", "disputes", ["match_id"])
    op.create_index("ix_disputes_user_id", "disputes", ["user_id"])
    op.create_index(
        "uq_disputes_match_user", "disputes", ["match_id", "user_id"], unique=True
    )

    # Allow the new `dispute_resolved` notification kind.
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('match_found', 'settled', 'refund', 'challenge_received', "
        "'challenge_accepted', 'friend_request', 'room_filled', "
        "'dispute_resolved', 'system')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('match_found', 'settled', 'refund', 'challenge_received', "
        "'challenge_accepted', 'friend_request', 'room_filled', 'system')",
    )
    op.drop_table("disputes")
