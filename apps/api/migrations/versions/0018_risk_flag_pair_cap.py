"""risk_flags.kind adds 'pair_cap'

Widens the `ck_risk_flags_kind` check to allow the derived `pair_cap` detector
(backlog · Phase 6 · derived risk detectors). `pair_cap` flags are informational
— surfaced in the admin risk queue, never blocking play — like `win_streak`,
whereas `sandbagging` flags still block metric wagers until cleared.

Revision ID: 0018_risk_flag_pair_cap
Revises: 0017_chat
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018_risk_flag_pair_cap"
down_revision: str | None = "0017_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_risk_flags_kind", "risk_flags", type_="check")
    op.create_check_constraint(
        "ck_risk_flags_kind",
        "risk_flags",
        "kind IN ('sandbagging', 'win_streak', 'pair_cap')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_risk_flags_kind", "risk_flags", type_="check")
    op.create_check_constraint(
        "ck_risk_flags_kind",
        "risk_flags",
        "kind IN ('sandbagging', 'win_streak')",
    )
