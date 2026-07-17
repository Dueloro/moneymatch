"""initial: users, feature_flags, admin_audit + flag/geo seeds

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 14 excluded ("Any Chance") states, as 2-letter codes matching
# users.residence_state. Sourced from poc-reference states.ts EXCLUDED_STATES.
EXCLUDED_STATE_CODES = [
    "AZ",
    "AR",
    "CT",
    "DE",
    "FL",
    "IN",
    "LA",
    "MD",
    "MN",
    "MT",
    "SC",
    "SD",
    "TN",
    "WY",
]

REGISTERED_GAMES = ["chess.lichess", "cs2.faceit", "dota2.opendota"]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("auth_id", sa.String(255), nullable=False),
        sa.Column("username", postgresql.CITEXT(), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("residence_state", sa.String(2), nullable=True),
        sa.Column(
            "dob_attested_18plus",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), server_default="user", nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column(
            "member_since",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.CheckConstraint(
            "status IN ('active', 'frozen', 'self_excluded')",
            name="ck_users_status",
        ),
        sa.UniqueConstraint("auth_id", name="uq_users_auth_id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
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
    )

    op.create_table(
        "admin_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(
            ["admin_id"], ["users.id"], name="fk_admin_audit_admin", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_admin_audit_admin_id", "admin_audit", ["admin_id"])

    _seed_flags()


def _seed_flags() -> None:
    flags = sa.table(
        "feature_flags",
        sa.column("key", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("payload", postgresql.JSONB),
    )
    rows: list[dict] = [
        {"key": "queue_paused", "enabled": False, "payload": {}},
        {"key": "settlement_paused", "enabled": False, "payload": {}},
        {
            "key": "geo_config",
            "enabled": True,
            "payload": {"excluded_states": EXCLUDED_STATE_CODES},
        },
    ]
    rows += [
        {"key": f"game:{game}", "enabled": True, "payload": {}}
        for game in REGISTERED_GAMES
    ]
    op.bulk_insert(flags, rows)


def downgrade() -> None:
    op.drop_index("ix_admin_audit_admin_id", table_name="admin_audit")
    op.drop_table("admin_audit")
    op.drop_table("feature_flags")
    op.drop_table("users")
