"""User aggregate (01-architecture §2 · Identity).

`auth_id` is the Supabase UID; the API provisions the row on first authed call.
`username` is the immutable public handle (citext-unique). Residence + 18+
attestation gate escrow (enforced server-side later), not sign-in.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

USER_ROLES = ("user", "admin")
USER_STATUSES = ("active", "frozen", "self_excluded")
# KYC verification lifecycle (10-phase-7 §1). `none` at MVP for everyone: the
# `kyc_required` policy hook returns False, so nothing advances this. The column
# + protocol exist so real KYC is an additive integration.
KYC_STATUSES = ("none", "pending", "verified", "failed")

# SQL backfill/backstop for `friend_code` (mirrors migration 0006); Python owns
# new rows via the `default` below. Postgres normalizes this function expression
# on read, so `alembic check` skips its server-default comparison (migrations/env.py).
_FRIEND_CODE_SERVER_DEFAULT = (
    "('MM-' || upper(substr(md5(gen_random_uuid()::text), 1, 6)))"
)

# Friend-code alphabet: base32 minus the ambiguous glyphs (0/O, 1/I). A short,
# immutable, shareable code (`MM-7F3K2Q`) so friends add each other without a
# scrapeable public username directory (08-phase-5 · deliverable 2).
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
    # Null until the user completes onboarding step 2; set once, then immutable.
    username: Mapped[str | None] = mapped_column(CITEXT(), unique=True, nullable=True)
    # Immutable shareable friend code (`MM-7F3K2Q`), minted at row creation.
    friend_code: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        default=gen_friend_code,
        server_default=text(_FRIEND_CODE_SERVER_DEFAULT),
        nullable=False,
    )
    # Presence-lite heartbeat: green dot when active in the last 5 min (08-phase-5).
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
    # KYC readiness seam (10-phase-7 §1). `none` for everyone at MVP; a real
    # KycProvider advances it once integration lands.
    kyc_status: Mapped[str] = mapped_column(
        String(16), default="none", server_default="none", nullable=False
    )
    member_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
