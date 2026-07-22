"""risk_flags.kind adds 'win_streak'

Widens the `ck_risk_flags_kind` check to allow the derived `win_streak` detector
(backlog · Phase B · derived risk detectors). `win_streak` flags are informational
— surfaced in the admin risk queue, never blocking play — whereas `sandbagging`
flags still block metric wagers until cleared.

Revision ID: 0009_risk_flag_kinds
Revises: 0008_kyc_status
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_risk_flag_kinds"
down_revision: str | None = "0008_kyc_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_risk_flags_kind", "risk_flags", type_="check")
    op.create_check_constraint(
        "ck_risk_flags_kind",
        "risk_flags",
        "kind IN ('sandbagging', 'win_streak')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_risk_flags_kind", "risk_flags", type_="check")
    op.create_check_constraint(
        "ck_risk_flags_kind",
        "risk_flags",
        "kind IN ('sandbagging')",
    )
