"""Add users.dismissed_checklists — per-game Play-tab checklist dismissals.

A player can dismiss a game's onboarding checklist card on the Play tab, and that
must survive reload and follow them across devices — so it lives on the user row,
not in localStorage. Symmetric with `active_games`: a JSONB list of catalog game
ids, defaulting to `[]`.

Additive and non-destructive: a new column with a `[]` server default, so every
existing row reads as "nothing dismissed". Alembic's version table keeps it from
re-applying; the add is guarded so a manual re-run is still safe.

Revision ID: 0027_dismissed_checklists
Revises: 0026_backfill_active_games
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027_dismissed_checklists"
down_revision: str | None = "0026_backfill_active_games"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS dismissed_checklists jsonb NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS dismissed_checklists")
