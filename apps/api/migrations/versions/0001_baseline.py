"""Baseline: the full chess-only schema, append-only guards, and seed flags.

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Rows here can never be updated or deleted.
APPEND_ONLY_TABLES = ("ledger_entries", "platform_ledger", "raw_payloads")

# Excluded ("any chance") states, matching users.residence_state.
EXCLUDED_STATES = [
    "AZ", "AR", "CT", "DE", "FL", "IN", "LA",
    "MD", "MN", "MT", "SC", "SD", "TN", "WY",
]  # fmt: skip

SEED_FLAGS = [
    {"key": "queue_paused", "enabled": False, "payload": {}},
    {"key": "settlement_paused", "enabled": False, "payload": {}},
    {"key": "worker_heartbeat", "enabled": False, "payload": {}},
    {
        "key": "geo_config",
        "enabled": True,
        "payload": {"excluded_states": EXCLUDED_STATES},
    },
    {"key": "game:chess.lichess", "enabled": True, "payload": {}},
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "conversations",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("kind IN ('dm', 'support')", name="ck_conversations_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_last_message_at",
        "conversations",
        ["last_message_at"],
        unique=False,
    )
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "live_snapshots",
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.UUID(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ref_type IN ('pool', 'match')", name="ck_live_snapshots_ref_type"
        ),
        sa.PrimaryKeyConstraint("ref_type", "ref_id"),
    )
    op.create_table(
        "platform_ledger",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("account", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.UUID(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account IN ('platform:rake', 'platform:promo')",
            name="ck_platform_ledger_account",
        ),
        sa.CheckConstraint(
            "ref_type IN ('match', 'solo_pool', 'tournament', 'admin', 'demo_rail')",
            name="ck_platform_ledger_ref_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_ledger_account"), "platform_ledger", ["account"], unique=False
    )
    op.create_index(
        op.f("ix_platform_ledger_created_at"),
        "platform_ledger",
        ["created_at"],
        unique=False,
    )
    op.create_table(
        "raw_payloads",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_raw_payloads_content_hash"),
        "raw_payloads",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_raw_payloads_fetched_at"), "raw_payloads", ["fetched_at"], unique=False
    )
    op.create_index(
        op.f("ix_raw_payloads_source"), "raw_payloads", ["source"], unique=False
    )
    op.create_table(
        "solo_pools",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("room_bar", sa.Float(), nullable=False),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_bps", sa.Integer(), nullable=False),
        sa.Column("room_size", sa.Integer(), nullable=False),
        sa.Column("min_entrants", sa.Integer(), nullable=False),
        sa.Column("pot_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("prize_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rake_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "state", sa.String(length=16), server_default="LOCKED", nullable=False
        ),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=True),
        sa.Column(
            "outcome_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_solo_pools_difficulty"
        ),
        sa.CheckConstraint(
            "state IN ('OPEN', 'LOCKED', 'SETTLED', 'CANCELED')",
            name="ck_solo_pools_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_solo_pools_entry_pos"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_solo_pools_window_ends_at"),
        "solo_pools",
        ["window_ends_at"],
        unique=False,
    )
    op.create_table(
        "tournaments",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("ranking_metric", sa.String(length=48), nullable=False),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_bps", sa.Integer(), nullable=False),
        sa.Column(
            "prize_split", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("field_size", sa.Integer(), nullable=False),
        sa.Column("min_field", sa.Integer(), nullable=False),
        sa.Column("min_ranked", sa.Integer(), nullable=False),
        sa.Column("pot_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("prize_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rake_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "state", sa.String(length=16), server_default="LOCKED", nullable=False
        ),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "standings_cache", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("standings_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine_version", sa.String(length=32), nullable=True),
        sa.Column(
            "outcome_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('OPEN', 'LOCKED', 'SETTLED', 'CANCELED')",
            name="ck_tournaments_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_tournaments_entry_pos"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tournaments_window_ends_at"),
        "tournaments",
        ["window_ends_at"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("auth_id", sa.String(length=255), nullable=False),
        sa.Column("username", postgresql.CITEXT(), nullable=True),
        sa.Column(
            "friend_code",
            sa.String(length=12),
            server_default=sa.text(
                "('MM-' || upper(substr(md5(gen_random_uuid()::text), 1, 6)))"
            ),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("residence_state", sa.String(length=2), nullable=True),
        sa.Column(
            "dob_attested_18plus", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="active", nullable=False
        ),
        sa.Column(
            "kyc_status", sa.String(length=16), server_default="none", nullable=False
        ),
        sa.Column(
            "member_since",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "dismissed_checklists",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "kyc_status IN ('none', 'pending', 'verified', 'failed')",
            name="ck_users_kyc_status",
        ),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.CheckConstraint(
            "status IN ('active', 'frozen', 'self_excluded')", name="ck_users_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_id"),
        sa.UniqueConstraint("friend_code"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "admin_audit",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("admin_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_audit_admin_id"), "admin_audit", ["admin_id"], unique=False
    )
    op.create_table(
        "conversation_members",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "user_id", name="uq_conversation_members_pair"
        ),
    )
    op.create_index(
        op.f("ix_conversation_members_conversation_id"),
        "conversation_members",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_members_user_id"),
        "conversation_members",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "disputes",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="open", nullable=False
        ),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "ref_type IN ('match', 'pool', 'tournament')", name="ck_disputes_ref_type"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'rejected')", name="ck_disputes_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_disputes_ref_id"), "disputes", ["ref_id"], unique=False)
    op.create_index(op.f("ix_disputes_user_id"), "disputes", ["user_id"], unique=False)
    op.create_index(
        "uq_disputes_ref_user",
        "disputes",
        ["ref_type", "ref_id", "user_id"],
        unique=True,
    )
    op.create_table(
        "friendships",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("friend_id", sa.UUID(), nullable=False),
        sa.Column(
            "state", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("blocked_by", sa.UUID(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('pending', 'accepted', 'blocked')", name="ck_friendships_state"
        ),
        sa.CheckConstraint("user_id <> friend_id", name="ck_friendships_no_self"),
        sa.ForeignKeyConstraint(["blocked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["friend_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "friend_id", name="uq_friendships_pair"),
    )
    op.create_index(
        op.f("ix_friendships_friend_id"), "friendships", ["friend_id"], unique=False
    )
    op.create_index(
        op.f("ix_friendships_user_id"), "friendships", ["user_id"], unique=False
    )
    op.create_table(
        "limits",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "daily_loss_cap_cents",
            sa.BigInteger(),
            server_default="20000",
            nullable=False,
        ),
        sa.Column(
            "daily_entry_cap_cents",
            sa.BigInteger(),
            server_default="50000",
            nullable=False,
        ),
        sa.Column(
            "daily_deposit_cap_cents",
            sa.BigInteger(),
            server_default="100000",
            nullable=False,
        ),
        sa.Column(
            "max_concurrent_contests", sa.Integer(), server_default="3", nullable=False
        ),
        sa.Column("timeout_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "pending_limits", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("pending_effective_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "linked_accounts",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("host_account_id", sa.String(length=128), nullable=False),
        sa.Column("host_username", sa.String(length=128), nullable=False),
        sa.Column(
            "link_method",
            sa.String(length=16),
            server_default="username",
            nullable=False,
        ),
        sa.Column(
            "profile_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default="active", nullable=False
        ),
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
        sa.CheckConstraint(
            "link_method IN ('username', 'oauth')",
            name="ck_linked_accounts_link_method",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'frozen', 'unbound')",
            name="ck_linked_accounts_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_linked_accounts_user_id"), "linked_accounts", ["user_id"], unique=False
    )
    op.create_index(
        "uq_linked_accounts_game_host",
        "linked_accounts",
        ["game", "host_account_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'unbound'"),
    )
    op.create_index(
        "uq_linked_accounts_user_game",
        "linked_accounts",
        ["user_id", "game"],
        unique=True,
        postgresql_where=sa.text("status <> 'unbound'"),
    )
    op.create_table(
        "matches",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("speed", sa.String(length=16), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_bps", sa.Integer(), nullable=False),
        sa.Column("pot_cents", sa.BigInteger(), nullable=False),
        sa.Column("prize_cents", sa.BigInteger(), nullable=False),
        sa.Column("rake_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "state", sa.String(length=16), server_default="PENDING", nullable=False
        ),
        sa.Column("friendly", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("host_game_id", sa.String(length=64), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "outcome_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("engine_version", sa.String(length=32), nullable=True),
        sa.Column("raw_payload_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('PENDING', 'ACTIVE', 'AWAITING_RESULT', 'SETTLED', "
            "'PUSHED', 'CANCELED')",
            name="ck_matches_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_matches_entry_pos"),
        sa.CheckConstraint(
            "pot_cents = prize_cents + rake_cents", name="ck_matches_econ_reconciles"
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"], ["raw_payloads.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matches_state"), "matches", ["state"], unique=False)
    op.create_index(
        op.f("ix_matches_window_ends_at"), "matches", ["window_ends_at"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=16), server_default="text", nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('text', 'invite', 'system')", name="ck_messages_kind"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_messages_sender_id"), "messages", ["sender_id"], unique=False
    )
    op.create_table(
        "metric_models",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("mu", sa.Float(), server_default="0", nullable=False),
        sa.Column("sigma", sa.Float(), server_default="0", nullable=False),
        sa.Column("n", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "game", "metric", name="uq_metric_models_user_game_metric"
        ),
    )
    op.create_index(
        op.f("ix_metric_models_user_id"), "metric_models", ["user_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "channel_sent",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('match_found', 'settled', 'refund', 'challenge_received', "
            "'challenge_accepted', 'friend_request', 'room_filled', "
            "'dispute_resolved', 'system')",
            name="ck_notifications_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notifications_created_at"),
        "notifications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False
    )
    op.create_table(
        "push_subscriptions",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"),
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "risk_flags",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("resolved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('sandbagging', 'win_streak', 'pair_cap')",
            name="ck_risk_flags_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_flags_created_at"), "risk_flags", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_risk_flags_user_id"), "risk_flags", ["user_id"], unique=False
    )
    op.create_table(
        "wallets",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "currency", sa.String(length=8), server_default="DEMO", nullable=False
        ),
        sa.Column(
            "available_cents", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("escrow_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "lifetime_net_cents", sa.BigInteger(), server_default="0", nullable=False
        ),
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
        sa.CheckConstraint(
            "currency IN ('DEMO', 'CASH', 'GEMS')", name="ck_wallets_currency"
        ),
        sa.CheckConstraint("available_cents >= 0", name="ck_wallets_available_nonneg"),
        sa.CheckConstraint("escrow_cents >= 0", name="ck_wallets_escrow_nonneg"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "currency", name="uq_wallets_user_currency"),
    )
    op.create_table(
        "challenges",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("challenger_id", sa.UUID(), nullable=False),
        sa.Column("challengee_id", sa.UUID(), nullable=True),
        sa.Column("invite_token", sa.String(length=64), nullable=True),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("speed", sa.String(length=16), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("friendly", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("state", sa.String(length=16), server_default="sent", nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=True),
        sa.Column("rematch_of", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('sent', 'accepted', 'declined', 'expired')",
            name="ck_challenges_state",
        ),
        sa.CheckConstraint(
            "(challengee_id IS NOT NULL) OR (invite_token IS NOT NULL)",
            name="ck_challenges_recipient",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_challenges_entry_pos"),
        sa.ForeignKeyConstraint(["challengee_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["challenger_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rematch_of"], ["matches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_token"),
    )
    op.create_index(
        op.f("ix_challenges_challengee_id"),
        "challenges",
        ["challengee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_challenges_challenger_id"),
        "challenges",
        ["challenger_id"],
        unique=False,
    )
    op.create_index(
        "ix_challenges_created_at", "challenges", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_challenges_expires_at"), "challenges", ["expires_at"], unique=False
    )
    op.create_table(
        "ledger_entries",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.Column("entry_type", sa.String(length=24), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "escrow_delta_cents", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.UUID(), nullable=True),
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('demo_deposit', 'demo_withdrawal', 'escrow_hold', "
            "'escrow_release', 'payout', 'rake', 'refund', 'adjustment')",
            name="ck_ledger_entry_type",
        ),
        sa.CheckConstraint(
            "ref_type IN ('match', 'solo_pool', 'tournament', 'admin', 'demo_rail')",
            name="ck_ledger_ref_type",
        ),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ledger_entries_created_at"),
        "ledger_entries",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ledger_entries_ref", "ledger_entries", ["ref_type", "ref_id"], unique=False
    )
    op.create_index(
        op.f("ix_ledger_entries_wallet_id"),
        "ledger_entries",
        ["wallet_id"],
        unique=False,
    )
    op.create_table(
        "match_players",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("linked_account_id", sa.UUID(), nullable=False),
        sa.Column("host_account_id", sa.String(length=128), nullable=False),
        sa.Column("color", sa.String(length=8), nullable=True),
        sa.Column("play_url", sa.String(length=256), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("stat_line", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["linked_account_id"], ["linked_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "user_id", name="uq_match_players_match_user"),
    )
    op.create_index(
        op.f("ix_match_players_match_id"), "match_players", ["match_id"], unique=False
    )
    op.create_index(
        op.f("ix_match_players_user_id"), "match_players", ["user_id"], unique=False
    )
    op.create_table(
        "queue_tickets",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("linked_account_id", sa.UUID(), nullable=False),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column(
            "product", sa.String(length=16), server_default="duel", nullable=False
        ),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("speed", sa.String(length=16), nullable=True),
        sa.Column("difficulty", sa.String(length=16), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("personal_bar", sa.Float(), nullable=True),
        sa.Column(
            "state", sa.String(length=16), server_default="waiting", nullable=False
        ),
        sa.Column("match_id", sa.UUID(), nullable=True),
        sa.Column("pool_id", sa.UUID(), nullable=True),
        sa.Column("tournament_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "product IN ('duel', 'pool', 'tournament')", name="ck_queue_tickets_product"
        ),
        sa.CheckConstraint(
            "state IN ('waiting', 'matched', 'canceled', 'expired')",
            name="ck_queue_tickets_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_queue_tickets_entry_pos"),
        sa.ForeignKeyConstraint(
            ["linked_account_id"], ["linked_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_queue_tickets_candidates",
        "queue_tickets",
        ["game", "market", "entry_cents", "state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_queue_tickets_expires_at"),
        "queue_tickets",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_queue_tickets_user_id"), "queue_tickets", ["user_id"], unique=False
    )
    op.create_table(
        "solo_entries",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("pool_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("linked_account_id", sa.UUID(), nullable=False),
        sa.Column("host_account_id", sa.String(length=128), nullable=False),
        sa.Column("personal_bar", sa.Float(), nullable=False),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default="LOCKED", nullable=False
        ),
        sa.Column("telemetry", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload_id", sa.UUID(), nullable=True),
        sa.Column("payout_cents", sa.BigInteger(), server_default="0", nullable=False),
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
        sa.CheckConstraint(
            "status IN ('LOCKED', 'CLEARED', 'MISSED', 'REFUNDED')",
            name="ck_solo_entries_status",
        ),
        sa.ForeignKeyConstraint(
            ["linked_account_id"], ["linked_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["pool_id"], ["solo_pools.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"], ["raw_payloads.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", "user_id", name="uq_solo_entries_pool_user"),
    )
    op.create_index(
        op.f("ix_solo_entries_pool_id"), "solo_entries", ["pool_id"], unique=False
    )
    op.create_index(
        op.f("ix_solo_entries_user_id"), "solo_entries", ["user_id"], unique=False
    )
    op.create_table(
        "tournament_entries",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("tournament_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("linked_account_id", sa.UUID(), nullable=False),
        sa.Column("host_account_id", sa.String(length=128), nullable=False),
        sa.Column(
            "baseline_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("matches_counted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default="LOCKED", nullable=False
        ),
        sa.Column("telemetry", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload_id", sa.UUID(), nullable=True),
        sa.Column("payout_cents", sa.BigInteger(), server_default="0", nullable=False),
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
        sa.CheckConstraint(
            "status IN ('LOCKED', 'RANKED', 'OUT', 'REFUNDED')",
            name="ck_tournament_entries_status",
        ),
        sa.ForeignKeyConstraint(
            ["linked_account_id"], ["linked_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"], ["raw_payloads.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"], ["tournaments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tournament_id", "user_id", name="uq_tournament_entries_tournament_user"
        ),
    )
    op.create_index(
        op.f("ix_tournament_entries_tournament_id"),
        "tournament_entries",
        ["tournament_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tournament_entries_user_id"),
        "tournament_entries",
        ["user_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION mm_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger is append-only: % on % is forbidden',
                TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION mm_reject_mutation()"
        )

    flags = sa.table(
        "feature_flags",
        sa.column("key", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("payload", postgresql.JSONB),
    )
    op.bulk_insert(flags, SEED_FLAGS)


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mm_reject_mutation()")

    op.drop_index(
        op.f("ix_tournament_entries_user_id"), table_name="tournament_entries"
    )
    op.drop_index(
        op.f("ix_tournament_entries_tournament_id"), table_name="tournament_entries"
    )
    op.drop_table("tournament_entries")
    op.drop_index(op.f("ix_solo_entries_user_id"), table_name="solo_entries")
    op.drop_index(op.f("ix_solo_entries_pool_id"), table_name="solo_entries")
    op.drop_table("solo_entries")
    op.drop_index(op.f("ix_queue_tickets_user_id"), table_name="queue_tickets")
    op.drop_index(op.f("ix_queue_tickets_expires_at"), table_name="queue_tickets")
    op.drop_index("ix_queue_tickets_candidates", table_name="queue_tickets")
    op.drop_table("queue_tickets")
    op.drop_index(op.f("ix_match_players_user_id"), table_name="match_players")
    op.drop_index(op.f("ix_match_players_match_id"), table_name="match_players")
    op.drop_table("match_players")
    op.drop_index(op.f("ix_ledger_entries_wallet_id"), table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_ref", table_name="ledger_entries")
    op.drop_index(op.f("ix_ledger_entries_created_at"), table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index(op.f("ix_challenges_expires_at"), table_name="challenges")
    op.drop_index("ix_challenges_created_at", table_name="challenges")
    op.drop_index(op.f("ix_challenges_challenger_id"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_challengee_id"), table_name="challenges")
    op.drop_table("challenges")
    op.drop_table("wallets")
    op.drop_index(op.f("ix_risk_flags_user_id"), table_name="risk_flags")
    op.drop_index(op.f("ix_risk_flags_created_at"), table_name="risk_flags")
    op.drop_table("risk_flags")
    op.drop_index(
        op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions"
    )
    op.drop_table("push_subscriptions")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_created_at"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_metric_models_user_id"), table_name="metric_models")
    op.drop_table("metric_models")
    op.drop_index(op.f("ix_messages_sender_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_matches_window_ends_at"), table_name="matches")
    op.drop_index(op.f("ix_matches_state"), table_name="matches")
    op.drop_table("matches")
    op.drop_index(
        "uq_linked_accounts_user_game",
        table_name="linked_accounts",
        postgresql_where=sa.text("status <> 'unbound'"),
    )
    op.drop_index(
        "uq_linked_accounts_game_host",
        table_name="linked_accounts",
        postgresql_where=sa.text("status <> 'unbound'"),
    )
    op.drop_index(op.f("ix_linked_accounts_user_id"), table_name="linked_accounts")
    op.drop_table("linked_accounts")
    op.drop_table("limits")
    op.drop_index(op.f("ix_friendships_user_id"), table_name="friendships")
    op.drop_index(op.f("ix_friendships_friend_id"), table_name="friendships")
    op.drop_table("friendships")
    op.drop_index("uq_disputes_ref_user", table_name="disputes")
    op.drop_index(op.f("ix_disputes_user_id"), table_name="disputes")
    op.drop_index(op.f("ix_disputes_ref_id"), table_name="disputes")
    op.drop_table("disputes")
    op.drop_index(
        op.f("ix_conversation_members_user_id"), table_name="conversation_members"
    )
    op.drop_index(
        op.f("ix_conversation_members_conversation_id"),
        table_name="conversation_members",
    )
    op.drop_table("conversation_members")
    op.drop_index(op.f("ix_admin_audit_admin_id"), table_name="admin_audit")
    op.drop_table("admin_audit")
    op.drop_table("users")
    op.drop_index(op.f("ix_tournaments_window_ends_at"), table_name="tournaments")
    op.drop_table("tournaments")
    op.drop_index(op.f("ix_solo_pools_window_ends_at"), table_name="solo_pools")
    op.drop_table("solo_pools")
    op.drop_index(op.f("ix_raw_payloads_source"), table_name="raw_payloads")
    op.drop_index(op.f("ix_raw_payloads_fetched_at"), table_name="raw_payloads")
    op.drop_index(op.f("ix_raw_payloads_content_hash"), table_name="raw_payloads")
    op.drop_table("raw_payloads")
    op.drop_index(op.f("ix_platform_ledger_created_at"), table_name="platform_ledger")
    op.drop_index(op.f("ix_platform_ledger_account"), table_name="platform_ledger")
    op.drop_table("platform_ledger")
    op.drop_table("live_snapshots")
    op.drop_table("feature_flags")
    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    op.drop_table("conversations")
