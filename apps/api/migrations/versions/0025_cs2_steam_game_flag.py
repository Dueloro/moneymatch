"""Seed game:cs2.steam and retire the game:cs2.faceit flag row.

Migration 0024 retired the `cs2.faceit` adapter but left its feature-flag row
behind, and nothing ever seeded a row for the game that replaced it. So the flag
table has an enabled row for a game that no longer exists, and no row at all for
the one that does — visible on the deployed API today, where
`/api/v1/health` reports `"game:cs2.faceit": true`.

Nothing is *broken* by that: `get_boolean_flags` falls back to `DEFAULT_FLAGS`
for a missing key, so CS2 reads as enabled, and the admin list synthesises a
detached row so it can still be toggled. The problem is operational. The
per-game kill switch for CS2 does not exist as a row until somebody toggles it,
so disabling CS2 during an incident — a Valve outage, a wedged Game
Coordinator, a suspected exploit — depends on an upsert going right under
pressure rather than on flipping a row that is already there. Every other
shipped game has a real row.

Found by diffing what the migration chain seeds against what the test fixture
seeds (AUDIT_FINDINGS.md P1-1).

Idempotent in both directions.

Revision ID: 0025_cs2_steam_game_flag
Revises: 0024_retire_cs2_faceit
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_cs2_steam_game_flag"
down_revision: str | None = "0024_retire_cs2_faceit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO feature_flags (key, enabled, payload) "
        "VALUES ('game:cs2.steam', true, '{}'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )
    # The adapter was removed in 0024; the row is now only misleading.
    op.execute("DELETE FROM feature_flags WHERE key = 'game:cs2.faceit'")


def downgrade() -> None:
    # Restore the faceit row as 0001 left it, so the chain round-trips.
    op.execute(
        "INSERT INTO feature_flags (key, enabled, payload) "
        "VALUES ('game:cs2.faceit', true, '{}'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute("DELETE FROM feature_flags WHERE key = 'game:cs2.steam'")
