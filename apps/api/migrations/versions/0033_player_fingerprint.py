"""player_fingerprint — identity signals for same-human / collusion detection

One row per (player, signal) — a device id, IP, or payment token the client
presented. Used to block two accounts that share a signal from co-entering the
same contest, and to surface likely-same-human pairs for admin review. Signals
are opaque, namespaced tokens ("device:...", "ip:..."); nothing here is PII by
itself.

Revision ID: 0033_player_fingerprint
Revises: 0032_player_streak
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_player_fingerprint"
down_revision: str | None = "0032_player_streak"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_fingerprint",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # An opaque, namespaced signal token, e.g. "device:abc", "ip:1.2.3.4".
        sa.Column("signal", sa.String(160), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "player_id", "signal", name="uq_player_fingerprint_player_signal"
        ),
    )
    # The reverse lookup ("which players share this signal?") is the collusion query.
    op.create_index(
        "ix_player_fingerprint_signal", "player_fingerprint", ["signal"]
    )


def downgrade() -> None:
    op.drop_table("player_fingerprint")
