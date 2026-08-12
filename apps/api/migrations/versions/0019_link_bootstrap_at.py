"""linked_accounts.models_bootstrapped_at

NULL means "metric-model bootstrap still owed". Deferred-host links (PUBG) leave
it NULL for the settlement worker to claim; cheap hosts bootstrap inline at link
and are stamped immediately. Existing rows are backfilled to now() so historical
accounts (already bootstrapped under the old code) aren't re-swept.

Revision ID: 0019_link_bootstrap_at
Revises: 0017_chat
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_link_bootstrap_at"
down_revision: str | None = "0017_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "linked_accounts",
        sa.Column("models_bootstrapped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE linked_accounts SET models_bootstrapped_at = now()")


def downgrade() -> None:
    op.drop_column("linked_accounts", "models_bootstrapped_at")
