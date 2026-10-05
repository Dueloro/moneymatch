"""bucket_contests — the wager path & room formation for bucketing (Phase 5)

Two tables:

- ``bucket_room``    — a formed room of same-bucket wagers settling against one
                       bar. Snapshots the reference version + bar it graded on,
                       so a later re-cut never changes how a past room settled.
- ``bucket_contest`` — one player's wager entry. Walks queued → matched →
                       awaiting_result → settled/refunded. The queue *is* the set
                       of rows with status='queued' and no room.

Both are inert until `bucketing_enabled` is on. Money still moves only through
`wallet_service`; these tables record *which* wager and *how it graded*, and the
authoritative money audit stays in `ledger_entries` + `settlement`.

Revision ID: 0029_bucket_contests
Revises: 0028_bucketing
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_bucket_contests"
down_revision: str | None = "0028_bucketing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bucket_room",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("bucket", sa.Integer, nullable=False),
        sa.Column("reference_season", sa.Integer, nullable=False),
        sa.Column("reference_version", sa.Integer, nullable=False),
        sa.Column("bar", sa.Float, nullable=False),
        sa.Column(
            "lower_is_better", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="'open'"),
        sa.Column("pot_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("rake_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_bucket_room_market",
        "bucket_room",
        ["game", "mode", "metric", "bucket", "status"],
    )

    op.create_table(
        "bucket_contest",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("bucket", sa.Integer, nullable=False),
        sa.Column("stake_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="'queued'"),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bucket_room.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Snapshotted at match time from the active reference.
        sa.Column("reference_season", sa.Integer, nullable=True),
        sa.Column("reference_version", sa.Integer, nullable=True),
        sa.Column("bar", sa.Float, nullable=True),
        # Filled at settlement.
        sa.Column("qualifying_match_id", sa.String(128), nullable=True),
        sa.Column("result_value", sa.Float, nullable=True),
        sa.Column("cleared", sa.Boolean, nullable=True),
        sa.Column("payout_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_bucket_contest_queue",
        "bucket_contest",
        ["game", "mode", "metric", "bucket", "status"],
    )
    op.create_index("ix_bucket_contest_player", "bucket_contest", ["player_id"])
    op.create_index("ix_bucket_contest_room", "bucket_contest", ["room_id"])
    # A player may hold at most one *open* (queued/matched/awaiting) contest per
    # market — enforced with a partial unique index so re-entry can't double-stake
    # the same market while one is still live.
    op.execute(
        "CREATE UNIQUE INDEX uq_bucket_contest_one_open "
        "ON bucket_contest (player_id, game, mode, metric) "
        "WHERE status IN ('queued','matched','awaiting_result');"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_bucket_contest_one_open;")
    op.drop_table("bucket_contest")
    op.drop_table("bucket_room")
