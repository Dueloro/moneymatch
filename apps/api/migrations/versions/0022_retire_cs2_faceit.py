"""Retire cs2.faceit — CS2 is the Steam game now

The FACEIT adapter is gone, so `registry.get('cs2.faceit')` raises. Anything
still pointing at that game id is either unusable or a live hazard, and the two
need opposite treatment.

**Deleted: the operational rows.** A skill model, a waiting queue ticket or an
injected demo match for a game with no adapter can never do anything except
fail. The ticket is the sharp one -- it would sit in the queue forever looking
for a room that can no longer form.

Linked accounts go only when nothing points at them. A settled entry holds a
reference to the account that played it, so deleting those would take the
history down with them; the survivors are invisible anyway, because `/links`
enumerates the catalog rather than the rows, and `cs2.faceit` has left it.

**Kept: settled history.** A contest that already paid out is a record of
something that happened, and rewriting its game id to `cs2.steam` would be
claiming it settled from a Steam scoreboard when it settled from FACEIT's API.
Nothing re-grades a terminal contest, so no adapter is ever resolved for these
rows; the web falls back to the raw id for an unknown game rather than breaking.

**Not handled here: contests still in flight.** Migrations must not move money.
Any non-terminal cs2.faceit contest has entries in escrow and has to be
cancelled through the engine's own refund path, which writes the ledger entries
this cannot. Verified none remained before this shipped.

Revision ID: 0022_retire_cs2_faceit
Revises: 0021_cs2_share_chain
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_retire_cs2_faceit"
down_revision: str | None = "0021_cs2_share_chain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAME = "cs2.faceit"

#: Rows that cannot function without an adapter. Tickets go first: they hold a
#: reference to the linked account, and nothing holds a reference to them.
DOOMED = ("queue_tickets", "metric_models", "simulated_matches")


def upgrade() -> None:
    bind = op.get_bind()

    # Refuse to run rather than strand money. If a contest is still open, its
    # entries are escrowed, and deleting the scaffolding underneath it would
    # leave players unable to be paid or refunded.
    for table in ("solo_pools", "tournaments", "matches"):
        open_rows = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} "  # noqa: S608 - fixed table names
                "WHERE game = :game AND state NOT IN "
                "('SETTLED', 'CANCELED', 'VOID', 'EXPIRED')"
            ),
            {"game": GAME},
        ).scalar_one()
        if open_rows:
            raise RuntimeError(
                f"{open_rows} {table} row(s) on {GAME} are still in flight. "
                "Cancel them through the engine so entries are refunded, then "
                "run this migration."
            )

    for table in DOOMED:
        exists = bind.execute(
            sa.text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
        ).scalar()
        if exists is None:
            continue
        bind.execute(
            sa.text(f"DELETE FROM {table} WHERE game = :game"),  # noqa: S608
            {"game": GAME},
        )

    # Linked accounts, but only the ones no history depends on. Which tables
    # point here is read from the schema rather than listed, so a later table
    # with its own reference cannot silently turn this into a failed migration
    # -- or worse, a cascade someone added to make the error go away.
    references = bind.execute(
        sa.text(
            "SELECT tc.table_name, kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON kcu.constraint_name = tc.constraint_name "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND ccu.table_name = 'linked_accounts'"
        )
    ).all()
    guards = " AND ".join(
        f"NOT EXISTS (SELECT 1 FROM {table} r WHERE r.{column} = la.id)"
        for table, column in references
    )
    bind.execute(
        sa.text(
            "DELETE FROM linked_accounts la WHERE la.game = :game"
            + (f" AND {guards}" if guards else "")
        ),
        {"game": GAME},
    )

    # A retired game must not linger in anyone's game bar. `active_games` is
    # jsonb, not a Postgres array, so this filters the elements rather than
    # reaching for array_remove.
    bind.execute(
        sa.text(
            "UPDATE users SET active_games = COALESCE(("
            "  SELECT jsonb_agg(g) FROM jsonb_array_elements(active_games) g"
            "  WHERE g <> to_jsonb(CAST(:game AS text))"
            "), '[]'::jsonb) "
            "WHERE active_games @> to_jsonb(ARRAY[CAST(:game AS text)])"
        ),
        {"game": GAME},
    )


def downgrade() -> None:
    """Deliberately empty.

    The deleted rows described accounts and skill models on a host integration
    that no longer exists in the codebase. Recreating them would produce records
    no adapter can serve, which is the state this migration exists to remove.
    """
