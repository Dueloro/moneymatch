"""cs2_share_chains — a player's cursor in Valve's share-code chain

Valve stores a player's matches as a linked list: given one share code they
own, `GetNextMatchSharingCode` returns the next. Persisting the cursor is what
removes the paste step, so a one-time setup turns into every future match
arriving on its own.

One row per user. A second cursor for the same account would race the first and
double-ingest every match, so the constraint lives in the database rather than
in a check some future caller can forget.

Revision ID: 0021_cs2_share_chain
Revises: 0020_cs2_matches
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_cs2_share_chain"
down_revision: str | None = "0020_cs2_matches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cs2_share_chains",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # CASCADE: a deleted user's cursor is meaningless, and leaving it would
        # keep polling Valve for an account nobody owns.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("steam_id", sa.String(20), nullable=False),
        # A per-user secret from Steam. It cannot spend anything, but it reads
        # match history, so it is never logged and never returned by the API.
        sa.Column("auth_code", sa.String(32), nullable=False),
        sa.Column("known_code", sa.String(40), nullable=False),
        sa.Column(
            "state", sa.String(16), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_code_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_cs2_share_chains_steam_id", "cs2_share_chains", ["steam_id"])


def downgrade() -> None:
    op.drop_index("ix_cs2_share_chains_steam_id", table_name="cs2_share_chains")
    op.drop_table("cs2_share_chains")
