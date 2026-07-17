"""queue_tickets, matches, match_players, notifications

Adds the head-to-head play substrate (01-architecture §2 · Play) — the PoC's
in-memory queue moves onto Postgres so pairing is race-safe under
`FOR UPDATE SKIP LOCKED` and survives a restart. `notifications` rows are written
now (Phase 3) and consumed by the Phase 5 Inbox.

None of these are append-only: tickets/matches transition and notifications get
`read_at`, so no `mm_reject_mutation` trigger is attached.

Revision ID: 0004_h2h_play
Revises: 0003_linking
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_h2h_play"
down_revision: str | None = "0003_linking"
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
    op.create_table(
        "queue_tickets",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("product", sa.String(16), server_default="duel", nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("speed", sa.String(16), nullable=True),
        sa.Column("difficulty", sa.String(16), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("personal_bar", sa.Float(), nullable=True),
        sa.Column("tolerance_stage", sa.Integer(), server_default="0", nullable=False),
        sa.Column("state", sa.String(16), server_default="waiting", nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "product IN ('duel', 'pool', 'tournament')",
            name="ck_queue_tickets_product",
        ),
        sa.CheckConstraint(
            "state IN ('waiting', 'matched', 'canceled', 'expired')",
            name="ck_queue_tickets_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_queue_tickets_entry_pos"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_queue_tickets_user", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["linked_account_id"],
            ["linked_accounts.id"],
            name="fk_queue_tickets_linked_account",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_queue_tickets_user_id", "queue_tickets", ["user_id"])
    op.create_index("ix_queue_tickets_expires_at", "queue_tickets", ["expires_at"])
    # The candidate-scan hot path: waiting tickets for a compatible bucket.
    op.create_index(
        "ix_queue_tickets_candidates",
        "queue_tickets",
        ["game", "market", "entry_cents", "state"],
    )

    op.create_table(
        "matches",
        _uuid_pk(),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("speed", sa.String(16), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_bps", sa.Integer(), nullable=False),
        sa.Column("pot_cents", sa.BigInteger(), nullable=False),
        sa.Column("prize_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_cents", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("brokered", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("host_game_id", sa.String(64), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome_detail", postgresql.JSONB(), nullable=True),
        sa.Column("engine_version", sa.String(32), nullable=True),
        sa.Column("raw_payload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('PENDING', 'ACTIVE', 'AWAITING_RESULT', "
            "'SETTLED', 'PUSHED', 'CANCELED')",
            name="ck_matches_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_matches_entry_pos"),
        sa.CheckConstraint(
            "pot_cents = prize_cents + rake_cents", name="ck_matches_econ_reconciles"
        ),
        sa.ForeignKeyConstraint(
            ["winner_user_id"],
            ["users.id"],
            name="fk_matches_winner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name="fk_matches_raw_payload",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_matches_state", "matches", ["state"])
    op.create_index("ix_matches_window_ends_at", "matches", ["window_ends_at"])

    op.create_table(
        "match_players",
        _uuid_pk(),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("color", sa.String(8), nullable=True),
        sa.Column("play_url", sa.String(256), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("stat_line", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("match_id", "user_id", name="uq_match_players_match_user"),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name="fk_match_players_match",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_match_players_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_account_id"],
            ["linked_accounts.id"],
            name="fk_match_players_linked_account",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_match_players_match_id", "match_players", ["match_id"])
    op.create_index("ix_match_players_user_id", "match_players", ["user_id"])

    op.create_table(
        "notifications",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('match_found', 'settled', 'challenge', 'refund', 'system')",
            name="ck_notifications_kind",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notifications_user",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_match_players_user_id", table_name="match_players")
    op.drop_index("ix_match_players_match_id", table_name="match_players")
    op.drop_table("match_players")
    op.drop_index("ix_matches_window_ends_at", table_name="matches")
    op.drop_index("ix_matches_state", table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_queue_tickets_candidates", table_name="queue_tickets")
    op.drop_index("ix_queue_tickets_expires_at", table_name="queue_tickets")
    op.drop_index("ix_queue_tickets_user_id", table_name="queue_tickets")
    op.drop_table("queue_tickets")
