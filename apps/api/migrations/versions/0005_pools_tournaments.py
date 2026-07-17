"""solo_pools, solo_entries, tournaments, tournament_entries, risk_flags

Adds the two async formats (07-phase-4). Pools and tournaments are queue-matched
rooms/fields formed from `queue_tickets` (`product` in pool/tournament), so this
also adds the `pool_id`/`tournament_id` back-refs to `queue_tickets`. Entries
escrow through the existing `ledger_entries` ref types (`solo_pool` / `tournament`,
already permitted by migration 0002). `risk_flags` is the sandbagging trail.

None of these are append-only (rooms/fields transition; entries grade in place).

Revision ID: 0005_pools_tournaments
Revises: 0004_h2h_play
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_pools_tournaments"
down_revision: str | None = "0004_h2h_play"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def upgrade() -> None:
    op.add_column(
        "queue_tickets",
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "queue_tickets",
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        # No pot=prize+rake check: for a pooled format the refunded (unverifiable)
        # entries are neither prize nor rake, so pot (= total entries) only equals
        # prize+rake+refunds. reconciliation_service enforces the money invariant.
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

    op.create_table(
        "tournaments",
        _uuid_pk(),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("ranking_metric", sa.String(48), nullable=False),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_bps", sa.Integer(), nullable=False),
        sa.Column("prize_split", postgresql.JSONB(), nullable=False),
        sa.Column("field_size", sa.Integer(), nullable=False),
        sa.Column("min_field", sa.Integer(), nullable=False),
        sa.Column("min_ranked", sa.Integer(), nullable=False),
        sa.Column("score_matches", sa.Integer(), nullable=False),
        sa.Column("pot_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("prize_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rake_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("state", sa.String(16), server_default="LOCKED", nullable=False),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("standings_cache", postgresql.JSONB(), nullable=True),
        sa.Column("standings_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine_version", sa.String(32), nullable=True),
        sa.Column("outcome_detail", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('OPEN', 'LOCKED', 'SETTLED', 'CANCELED')",
            name="ck_tournaments_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_tournaments_entry_pos"),
        # No pot=prize+rake check (see solo_pools): refunds live outside prize+rake.
    )
    op.create_index("ix_tournaments_window_ends_at", "tournaments", ["window_ends_at"])

    op.create_table(
        "tournament_entries",
        _uuid_pk(),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column(
            "baseline_snapshot", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("matches_counted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), server_default="LOCKED", nullable=False),
        sa.Column("telemetry", postgresql.JSONB(), nullable=True),
        sa.Column("raw_payload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payout_cents", sa.BigInteger(), server_default="0", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "tournament_id", "user_id", name="uq_tournament_entries_tournament_user"
        ),
        sa.CheckConstraint(
            "status IN ('LOCKED', 'RANKED', 'OUT', 'REFUNDED')",
            name="ck_tournament_entries_status",
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name="fk_tournament_entries_tournament",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tournament_entries_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_account_id"],
            ["linked_accounts.id"],
            name="fk_tournament_entries_linked_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name="fk_tournament_entries_raw_payload",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_tournament_entries_tournament_id", "tournament_entries", ["tournament_id"]
    )
    op.create_index("ix_tournament_entries_user_id", "tournament_entries", ["user_id"])

    op.create_table(
        "risk_flags",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('sandbagging')", name="ck_risk_flags_kind"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_risk_flags_user", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_risk_flags_user_id", "risk_flags", ["user_id"])
    op.create_index("ix_risk_flags_created_at", "risk_flags", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_risk_flags_created_at", table_name="risk_flags")
    op.drop_index("ix_risk_flags_user_id", table_name="risk_flags")
    op.drop_table("risk_flags")
    op.drop_index("ix_tournament_entries_user_id", table_name="tournament_entries")
    op.drop_index(
        "ix_tournament_entries_tournament_id", table_name="tournament_entries"
    )
    op.drop_table("tournament_entries")
    op.drop_index("ix_tournaments_window_ends_at", table_name="tournaments")
    op.drop_table("tournaments")
    op.drop_index("ix_solo_entries_user_id", table_name="solo_entries")
    op.drop_index("ix_solo_entries_pool_id", table_name="solo_entries")
    op.drop_table("solo_entries")
    op.drop_index("ix_solo_pools_window_ends_at", table_name="solo_pools")
    op.drop_table("solo_pools")
    op.drop_column("queue_tickets", "tournament_id")
    op.drop_column("queue_tickets", "pool_id")
