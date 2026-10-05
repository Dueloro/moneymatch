"""Permanent settlement log for tournaments.

- `tournament_results`: one row per entrant at settlement (score, rank, payout,
  outcome, username snapshot).
- `tournament_match_log`: one row per (entrant, fetched match) with the verdict
  the rules gave it and its host/fetch timestamps.

Both append-only (trigger). Additive only.

Revision ID: 0035_tournament_settlement_log
Revises: 0034_game_matches_rolling
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from moneymatch_api.db.append_only import trigger_ddl

revision: str = "0035_tournament_settlement_log"
down_revision: str | None = "0034_game_matches_rolling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)


def _id() -> sa.Column:
    return sa.Column(
        "id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _tournament_fk() -> sa.Column:
    return sa.Column(
        "tournament_id",
        _UUID,
        sa.ForeignKey("tournaments.id", ondelete="RESTRICT"),
        nullable=False,
    )


def _recorded_at() -> sa.Column:
    return sa.Column(
        "recorded_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("clock_timestamp()"),
    )


def upgrade() -> None:
    op.create_table(
        "tournament_results",
        _id(),
        _tournament_fk(),
        sa.Column("entry_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("matches_counted", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("payout_cents", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("tournament_outcome", sa.String(48), nullable=True),
        _recorded_at(),
        sa.UniqueConstraint(
            "tournament_id", "entry_id", name="uq_tournament_results_entry"
        ),
    )
    op.create_index(
        "ix_tournament_results_tournament_id", "tournament_results", ["tournament_id"]
    )
    op.create_index("ix_tournament_results_user_id", "tournament_results", ["user_id"])
    op.execute(trigger_ddl("tournament_results"))

    op.create_table(
        "tournament_match_log",
        _id(),
        _tournament_fk(),
        sa.Column("entry_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column(
            "game_match_id",
            _UUID,
            sa.ForeignKey("game_matches.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("host_match_id", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(32), nullable=True),
        sa.Column("result", sa.String(8), nullable=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("counted", sa.Boolean(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        _recorded_at(),
        sa.UniqueConstraint(
            "tournament_id",
            "entry_id",
            "host_match_id",
            name="uq_tournament_match_log_entry_match",
        ),
    )
    op.create_index(
        "ix_tournament_match_log_tournament_id",
        "tournament_match_log",
        ["tournament_id"],
    )
    op.create_index(
        "ix_tournament_match_log_user_id", "tournament_match_log", ["user_id"]
    )
    op.create_index(
        "ix_tournament_match_log_host_match_id",
        "tournament_match_log",
        ["host_match_id"],
    )
    op.execute(trigger_ddl("tournament_match_log"))


def downgrade() -> None:
    for table in ("tournament_match_log", "tournament_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.drop_table(table)
