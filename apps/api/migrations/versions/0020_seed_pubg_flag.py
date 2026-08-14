"""Seed the game:pubg.steam feature flag.

The initial migration hard-coded only chess/cs2/dota2. PUBG defaults to enabled
(absent flag ⇒ on), but seeding the row gives admin a toggle target and matches
the "seed each game flag in a migration" convention. Idempotent.

Revision ID: 0020_seed_pubg_flag
Revises: 0019_link_bootstrap_at
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_seed_pubg_flag"
down_revision: str | None = "0019_link_bootstrap_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO feature_flags (key, enabled, payload) "
        "VALUES ('game:pubg.steam', true, '{}'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'game:pubg.steam'")
