"""Stored match history + rolling tournaments.

- `game_matches`: one row per (host account, host match), written by the
  background ingester and read by tournament scoring. Append-only (trigger), and
  idempotent through the (game, host_account_id, host_match_id) unique key.
- `linked_accounts.ingest_*`: the ingester's per-account bookkeeping.
- `tournaments.join_closes_at`: when a rolling tournament stops taking joiners.

Additive only; nothing existing is rewritten.

Sits after the bucketing migrations (0028-0033, copied verbatim from
feat/bucket_system) so both branches share one linear chain. It does not
depend on them. `0034_drop_solo_pools` is deliberately not on this branch,
which still settles existing pools.

Revision ID: 0034_game_matches_rolling
Revises: 0033_player_fingerprint
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from moneymatch_api.db.append_only import trigger_ddl

revision: str = "0034_game_matches_rolling"
down_revision: str | None = "0033_player_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "game_matches"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "linked_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("linked_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("host_match_id", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(32), nullable=True),
        sa.Column("rated", sa.Boolean(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("result", sa.String(8), nullable=True),
        sa.Column("moves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint(
            "game",
            "host_account_id",
            "host_match_id",
            name="uq_game_matches_account_match",
        ),
    )
    op.create_index("ix_game_matches_user_id", _TABLE, ["user_id"])
    op.create_index("ix_game_matches_fetched_at", _TABLE, ["fetched_at"])
    op.create_index(
        "ix_game_matches_account_started",
        _TABLE,
        ["game", "host_account_id", "started_at"],
    )
    # Stored results are evidence: never edited, never deleted.
    op.execute(trigger_ddl(_TABLE))

    op.add_column(
        "linked_accounts",
        sa.Column("ingest_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "linked_accounts",
        sa.Column("ingest_polled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "linked_accounts",
        sa.Column("ingest_cursor_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tournaments",
        sa.Column("join_closes_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "join_closes_at")
    op.drop_column("linked_accounts", "ingest_cursor_ms")
    op.drop_column("linked_accounts", "ingest_polled_at")
    op.drop_column("linked_accounts", "ingest_attempted_at")
    op.execute(f"DROP TRIGGER IF EXISTS {_TABLE}_append_only ON {_TABLE}")
    op.drop_table(_TABLE)
