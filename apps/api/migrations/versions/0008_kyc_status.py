"""users.kyc_status (payments/KYC readiness)

Adds the `kyc_status` column (`none|pending|verified|failed`, default `none`)
backing the Phase-7 KYC seam (10-phase-7 §1). Every existing row backfills to
`none`; the `kyc_required` policy hook returns False at MVP so nothing advances
it. The column exists so real KYC integration is additive.

Revision ID: 0008_kyc_status
Revises: 0007_admin_ops
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_kyc_status"
down_revision: str | None = "0007_admin_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "kyc_status",
            sa.String(length=16),
            server_default="none",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_kyc_status",
        "users",
        "kyc_status IN ('none', 'pending', 'verified', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_kyc_status", "users", type_="check")
    op.drop_column("users", "kyc_status")
