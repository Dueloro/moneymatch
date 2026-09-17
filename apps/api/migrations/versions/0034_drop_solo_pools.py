"""drop solo_pools, solo_entries, and queue_tickets.pool_id

Retires the Solo-Pool ("bar") format. The product is now peer-to-peer only —
1v1 head-to-head + tournaments — so the pooled-wager tables and the queue-ticket
back-ref to a pool are removed. Match and tournament money paths are untouched.

Safe to drop outright: pools were behind a removed surface and carry no data any
launched deployment relies on. `downgrade` faithfully recreates both tables and
the column (mirrors 0005) so the migration is reversible.

Revision ID: 0034_drop_solo_pools
Revises: 0033_player_fingerprint
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_drop_solo_pools"
down_revision: str | None = "0033_player_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_solo_entries_user_id", table_name="solo_entries")
    op.drop_index("ix_solo_entries_pool_id", table_name="solo_entries")
    op.drop_table("solo_entries")
    op.drop_index("ix_solo_pools_window_ends_at", table_name="solo_pools")
    op.drop_table("solo_pools")
    op.drop_column("queue_tickets", "pool_id")


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        primary_key=True,
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def downgrade() -> None:
    op.add_column(
        "queue_tickets",
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "solo_pools",
        _uuid_pk(),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("room_bar", sa.Float(), nullable=False),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_bps", sa.Integer(), nullable=False),
        sa.Column("room_size", sa.Integer(), nullable=False),
        sa.Column("min_entrants", sa.Integer(), nullable=False),
        sa.Column("pot_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("prize_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rake_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("state", sa.String(16), server_default="LOCKED", nullable=False),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=True),
        sa.Column("outcome_detail", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_solo_pools_difficulty"
        ),
        sa.CheckConstraint(
            "state IN ('OPEN', 'LOCKED', 'SETTLED', 'CANCELED')",
            name="ck_solo_pools_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_solo_pools_entry_pos"),
    )
    op.create_index("ix_solo_pools_window_ends_at", "solo_pools", ["window_ends_at"])
    op.create_table(
        "solo_entries",
        _uuid_pk(),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("personal_bar", sa.Float(), nullable=False),
        sa.Column(
            "baseline_snapshot", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("status", sa.String(16), server_default="LOCKED", nullable=False),
        sa.Column("telemetry", postgresql.JSONB(), nullable=True),
        sa.Column("raw_payload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payout_cents", sa.BigInteger(), server_default="0", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("pool_id", "user_id", name="uq_solo_entries_pool_user"),
        sa.CheckConstraint(
            "status IN ('LOCKED', 'CLEARED', 'MISSED', 'REFUNDED')",
            name="ck_solo_entries_status",
        ),
        sa.ForeignKeyConstraint(
            ["pool_id"],
            ["solo_pools.id"],
            name="fk_solo_entries_pool",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_solo_entries_user", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["linked_account_id"],
            ["linked_accounts.id"],
            name="fk_solo_entries_linked_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name="fk_solo_entries_raw_payload",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_solo_entries_pool_id", "solo_entries", ["pool_id"])
    op.create_index("ix_solo_entries_user_id", "solo_entries", ["user_id"])
