"""friendships, challenges; users.friend_code/last_seen_at; matches.friendly;
notifications kind + channel_sent

Adds the Phase 5 social layer (08-phase-5). `friendships` and `challenges` are
new tables; `users` gains an immutable `friend_code` + a presence heartbeat;
`matches` gains the zero-rake `friendly` flag; `notifications` widens its `kind`
check to the consolidated fan-out set and carries `channel_sent` for post-MVP
email/push. None of the new tables are append-only (they transition in place).

Revision ID: 0006_social
Revises: 0005_pools_tournaments
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_social"
down_revision: str | None = "0005_pools_tournaments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The consolidated notification kinds (must match models/notification.py).
_NOTIFICATION_KINDS = (
    "match_found",
    "settled",
    "refund",
    "challenge_received",
    "challenge_accepted",
    "friend_request",
    "room_filled",
    "system",
)
_KIND_SQL = ", ".join(f"'{k}'" for k in _NOTIFICATION_KINDS)

# Backfill/backstop friend-code generator in SQL (Python owns new rows via the
# ORM default; this keeps raw inserts + existing rows valid).
_FRIEND_CODE_DEFAULT = "('MM-' || upper(substr(md5(gen_random_uuid()::text), 1, 6)))"


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
    # --- users: friend_code + presence heartbeat ------------------------- #
    op.add_column(
        "users",
        sa.Column(
            "friend_code",
            sa.String(12),
            server_default=sa.text(_FRIEND_CODE_DEFAULT),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_users_friend_code", "users", ["friend_code"])
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- matches: zero-rake friendly flag -------------------------------- #
    op.add_column(
        "matches",
        sa.Column(
            "friendly",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # --- notifications: widen kind + channel_sent ------------------------ #
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind", "notifications", f"kind IN ({_KIND_SQL})"
    )
    op.add_column(
        "notifications",
        sa.Column(
            "channel_sent",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )

    # --- friendships ----------------------------------------------------- #
    op.create_table(
        "friendships",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("friend_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(16), server_default="pending", nullable=False),
        sa.Column("blocked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "friend_id", name="uq_friendships_pair"),
        sa.CheckConstraint("user_id <> friend_id", name="ck_friendships_no_self"),
        sa.CheckConstraint(
            "state IN ('pending', 'accepted', 'blocked')", name="ck_friendships_state"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_friendships_user", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["friend_id"],
            ["users.id"],
            name="fk_friendships_friend",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["blocked_by"],
            ["users.id"],
            name="fk_friendships_blocked_by",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_friendships_user_id", "friendships", ["user_id"])
    op.create_index("ix_friendships_friend_id", "friendships", ["friend_id"])

    # --- challenges ------------------------------------------------------ #
    op.create_table(
        "challenges",
        _uuid_pk(),
        sa.Column("challenger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("challengee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invite_token", sa.String(64), nullable=True),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("speed", sa.String(16), nullable=True),
        sa.Column("entry_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "friendly", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("state", sa.String(16), server_default="sent", nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rematch_of", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("invite_token", name="uq_challenges_invite_token"),
        sa.CheckConstraint(
            "state IN ('sent', 'accepted', 'declined', 'expired')",
            name="ck_challenges_state",
        ),
        sa.CheckConstraint("entry_cents > 0", name="ck_challenges_entry_pos"),
        sa.CheckConstraint(
            "(challengee_id IS NOT NULL) OR (invite_token IS NOT NULL)",
            name="ck_challenges_recipient",
        ),
        sa.ForeignKeyConstraint(
            ["challenger_id"],
            ["users.id"],
            name="fk_challenges_challenger",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["challengee_id"],
            ["users.id"],
            name="fk_challenges_challengee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name="fk_challenges_match", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["rematch_of"],
            ["matches.id"],
            name="fk_challenges_rematch_of",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_challenges_challenger_id", "challenges", ["challenger_id"])
    op.create_index("ix_challenges_challengee_id", "challenges", ["challengee_id"])
    op.create_index("ix_challenges_expires_at", "challenges", ["expires_at"])
    op.create_index("ix_challenges_created_at", "challenges", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_challenges_created_at", table_name="challenges")
    op.drop_index("ix_challenges_expires_at", table_name="challenges")
    op.drop_index("ix_challenges_challengee_id", table_name="challenges")
    op.drop_index("ix_challenges_challenger_id", table_name="challenges")
    op.drop_table("challenges")
    op.drop_index("ix_friendships_friend_id", table_name="friendships")
    op.drop_index("ix_friendships_user_id", table_name="friendships")
    op.drop_table("friendships")

    op.drop_column("notifications", "channel_sent")
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('match_found', 'settled', 'challenge', 'refund', 'system')",
    )

    op.drop_column("matches", "friendly")
    op.drop_column("users", "last_seen_at")
    op.drop_constraint("uq_users_friend_code", "users", type_="unique")
    op.drop_column("users", "friend_code")
