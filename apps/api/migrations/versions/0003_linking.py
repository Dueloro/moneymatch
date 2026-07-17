"""linked_accounts, metric_models, raw_payloads

Adds the identity-linking + skill/audit substrate (01-architecture §2).
`linked_accounts` enforces immutable, non-shareable bindings via two unique
constraints. `raw_payloads` is append-only (the `mm_reject_mutation` trigger
function was created in 0002; here we just attach a trigger).

Revision ID: 0003_linking
Revises: 0002_wallet_ledger
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from moneymatch_api.db.append_only import trigger_ddl

revision: str = "0003_linking"
down_revision: str | None = "0002_wallet_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RAW_PAYLOADS = "raw_payloads"


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
        "linked_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("host_account_id", sa.String(128), nullable=False),
        sa.Column("host_username", sa.String(128), nullable=False),
        sa.Column(
            "link_method", sa.String(16), server_default="username", nullable=False
        ),
        sa.Column(
            "profile_snapshot",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "link_method IN ('username', 'oauth')",
            name="ck_linked_accounts_link_method",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'frozen')", name="ck_linked_accounts_status"
        ),
        sa.UniqueConstraint("user_id", "game", name="uq_linked_accounts_user_game"),
        sa.UniqueConstraint(
            "game", "host_account_id", name="uq_linked_accounts_game_host"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_linked_accounts_user",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_linked_accounts_user_id", "linked_accounts", ["user_id"]
    )

    op.create_table(
        "metric_models",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("mu", sa.Float(), server_default="0", nullable=False),
        sa.Column("sigma", sa.Float(), server_default="0", nullable=False),
        sa.Column("n", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "user_id", "game", "metric", name="uq_metric_models_user_game_metric"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_metric_models_user",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_metric_models_user_id", "metric_models", ["user_id"])

    op.create_table(
        _RAW_PAYLOADS,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("memo", sa.Text(), nullable=True),
    )
    op.create_index("ix_raw_payloads_source", _RAW_PAYLOADS, ["source"])
    op.create_index("ix_raw_payloads_content_hash", _RAW_PAYLOADS, ["content_hash"])
    op.create_index("ix_raw_payloads_fetched_at", _RAW_PAYLOADS, ["fetched_at"])

    # raw_payloads is append-only (audit). The trigger function exists from 0002.
    op.execute(trigger_ddl(_RAW_PAYLOADS))


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_RAW_PAYLOADS}_append_only ON {_RAW_PAYLOADS}")
    op.drop_index("ix_raw_payloads_fetched_at", table_name=_RAW_PAYLOADS)
    op.drop_index("ix_raw_payloads_content_hash", table_name=_RAW_PAYLOADS)
    op.drop_index("ix_raw_payloads_source", table_name=_RAW_PAYLOADS)
    op.drop_table(_RAW_PAYLOADS)
    op.drop_index("ix_metric_models_user_id", table_name="metric_models")
    op.drop_table("metric_models")
    op.drop_index("ix_linked_accounts_user_id", table_name="linked_accounts")
    op.drop_table("linked_accounts")
