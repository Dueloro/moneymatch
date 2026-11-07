"""User aggregate."""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

USER_ROLES = ("user", "admin")
USER_STATUSES = ("active", "frozen", "self_excluded")
KYC_STATUSES = ("none", "pending", "verified", "failed")

_FRIEND_CODE_SERVER_DEFAULT = (
    "('MM-' || upper(substr(md5(gen_random_uuid()::text), 1, 6)))"
)

_FRIEND_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_FRIEND_CODE_LEN = 6


def gen_friend_code() -> str:
    body = "".join(
        secrets.choice(_FRIEND_CODE_ALPHABET) for _ in range(_FRIEND_CODE_LEN)
    )
    return f"MM-{body}"


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "status IN ('active', 'frozen', 'self_excluded')",
            name="ck_users_status",
        ),
        CheckConstraint(
            "kyc_status IN ('none', 'pending', 'verified', 'failed')",
            name="ck_users_kyc_status",
        ),
    )

    id = uuid_pk()
    auth_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(CITEXT(), unique=True, nullable=True)
    friend_code: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        default=gen_friend_code,
        server_default=text(_FRIEND_CODE_SERVER_DEFAULT),
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    residence_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    dob_attested_18plus: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(16), default="user", server_default="user", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False
    )
    kyc_status: Mapped[str] = mapped_column(
        String(16), default="none", server_default="none", nullable=False
    )
    member_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    dismissed_checklists: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
