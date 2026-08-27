"""Backfill users.active_games so app-wide game gating is correct on rollout.

`active_games` (the player's "play set") is the single source of truth for which
games render across the app. Until now an **empty** set meant "not chosen yet",
and the client fell back to showing *every* registered game — so an existing user
with `active_games = []` is silently un-gated: the Play/H2H/Tournament switchers
show all four games regardless. Once the selection overlay ships and gating reads
this field strictly, those users would either see everything (no gate) or, worse,
have games they actively use disappear behind a Chess-only default.

This backfills every user whose set is still empty:

- to the distinct **games they currently have a real link to** (`status <> 'unbound'`),
  restricted to the live catalog so a retired binding (e.g. `cs2.faceit`) is never
  written into the play set;
- falling back to **`["chess.lichess"]`** when they have no live link, so the set
  is never empty and Chess (the launch game) is always available.

CS2/PUBG links are preserved even though those games are beta-locked for *adding*
new games in production — gating reads `active_games` directly, so a user already
linked to CS2 keeps CS2. The lock only limits adding games that aren't yours yet.

Only rows with an empty/absent set are touched, so this is **idempotent**: a
user who has already chosen games (non-empty array) is never overwritten, and the
migration is safe to re-run.

Revision ID: 0026_backfill_active_games
Revises: 0025_cs2_steam_game_flag
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_backfill_active_games"
down_revision: str | None = "0025_cs2_steam_game_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The live catalog (REGISTERED_GAMES). A backfill must not depend on Python
# constants that can change later, so the ids are pinned here as of this revision.
_CATALOG = "'chess.lichess', 'cs2.steam', 'dota2.opendota', 'pubg.steam'"

_BACKFILL = f"""
    UPDATE users u
    SET active_games = COALESCE(
        (
            SELECT jsonb_agg(DISTINCT la.game)
            FROM linked_accounts la
            WHERE la.user_id = u.id
              AND la.status <> 'unbound'
              AND la.game IN ({_CATALOG})
        ),
        '["chess.lichess"]'::jsonb
    )
    WHERE u.active_games IS NULL
       OR jsonb_typeof(u.active_games) <> 'array'
       OR jsonb_array_length(u.active_games) = 0
"""


def upgrade() -> None:
    op.execute(_BACKFILL)


def downgrade() -> None:
    # Data-only backfill: we cannot tell which rows were empty before it ran, so
    # there is nothing safe to reverse. Emptying every set again would be a
    # destructive guess, not a round-trip. No schema changed, so the chain still
    # round-trips cleanly.
    pass
