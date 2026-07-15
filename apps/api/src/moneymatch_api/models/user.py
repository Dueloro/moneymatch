"""User aggregate (01-architecture §2 · Identity).

`auth_id` is the Supabase UID; the API provisions the row on first authed call.
`username` is the immutable public handle (citext-unique). Residence + 18+
attestation gate escrow (enforced server-side later), not sign-in.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk

USER_ROLES = ("user", "admin")
USER_STATUSES = ("active", "frozen", "self_excluded")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "status IN ('active', 'frozen', 'self_excluded')",
            name="ck_users_status",
        ),
    )

    id = uuid_pk()
    auth_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Null until the user completes onboarding step 2; set once, then immutable.
    username: Mapped[str | None] = mapped_column(CITEXT(), unique=True, nullable=True)
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
    member_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
