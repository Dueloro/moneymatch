"""wallets, ledger_entries (append-only), platform_ledger, limits

Adds the money substrate (01-architecture §2 · Money). `ledger_entries` and
`platform_ledger` are append-only: a trigger rejects UPDATE/DELETE at the DB
level so the audit trail is immutable regardless of the code path.

Revision ID: 0002_wallet_ledger
Revises: 0001_initial
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from moneymatch_api.db.append_only import APPEND_ONLY_TABLES, install_statements

revision: str = "0002_wallet_ledger"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "wallets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(8), server_default="DEMO", nullable=False),
        sa.Column(
            "available_cents", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("escrow_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "lifetime_net_cents", sa.BigInteger(), server_default="0", nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "currency IN ('DEMO', 'CASH', 'GEMS')", name="ck_wallets_currency"
        ),
        sa.CheckConstraint("available_cents >= 0", name="ck_wallets_available_nonneg"),
        sa.CheckConstraint("escrow_cents >= 0", name="ck_wallets_escrow_nonneg"),
        sa.UniqueConstraint("user_id", "currency", name="uq_wallets_user_currency"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_wallets_user", ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "escrow_delta_cents", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("ref_type", sa.String(16), nullable=False),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
            name="fk_ledger_wallet",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_ledger_entries_wallet_id", "ledger_entries", ["wallet_id"])
    op.create_index("ix_ledger_entries_created_at", "ledger_entries", ["created_at"])
    op.create_index("ix_ledger_entries_ref", "ledger_entries", ["ref_type", "ref_id"])

    op.create_table(
        "platform_ledger",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("account", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("ref_type", sa.String(16), nullable=False),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
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
    )
    op.create_index("ix_platform_ledger_account", "platform_ledger", ["account"])
    op.create_index("ix_platform_ledger_created_at", "platform_ledger", ["created_at"])

    op.create_table(
        "limits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "max_concurrent_contests",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column("pending_limits", postgresql.JSONB(), nullable=True),
        sa.Column("pending_effective_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("user_id", name="uq_limits_user"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_limits_user", ondelete="RESTRICT"
        ),
    )

    for statement in install_statements():
        op.execute(statement)


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mm_reject_mutation()")
    op.drop_table("limits")
    op.drop_index("ix_platform_ledger_created_at", table_name="platform_ledger")
    op.drop_index("ix_platform_ledger_account", table_name="platform_ledger")
    op.drop_table("platform_ledger")
    op.drop_index("ix_ledger_entries_ref", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_created_at", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_wallet_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("wallets")
