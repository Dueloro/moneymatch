"""User / onboarding schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_PATTERN = r"^[a-z0-9_]{3,20}$"
STATE_PATTERN = r"^[A-Za-z]{2}$"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str | None
    email: str | None
    friend_code: str
    residence_state: str | None
    dob_attested_18plus: bool
    role: str
    status: str
    member_since: datetime


class LimitsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    daily_loss_cap_cents: int
    daily_entry_cap_cents: int
    max_concurrent_contests: int
    pending_limits: dict | None
    pending_effective_at: datetime | None


class MeResponse(BaseModel):
    """`/me` payload: the user, a computed onboarding flag, and staking limits."""

    user: UserResponse
    needs_onboarding: bool
    limits: LimitsResponse | None = None
    unread_notifications: int = 0  # sidebar bell dot (08-phase-5)


class UpdateMeRequest(BaseModel):
    """Onboarding (username + state + 18+, set once) and/or limit edits.

    All fields optional so the endpoint serves both onboarding and later limit
    changes. Lowering a cap is instant; raising is delayed (see limits_service).
    """

    username: str | None = Field(default=None, description="3–20 chars [a-z0-9_]; once")
    residence_state: str | None = Field(default=None, description="2-letter US state")
    dob_attested_18plus: bool | None = None
    daily_loss_cap_cents: int | None = Field(default=None, gt=0)
    daily_entry_cap_cents: int | None = Field(default=None, gt=0)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str | None) -> str | None:
        if v is None:
            return None
        import re

        v = v.strip().lower()
        if not re.match(USERNAME_PATTERN, v):
            raise ValueError(
                "Username must be 3–20 characters of lowercase letters, "
                "digits, or underscores."
            )
        return v

    @field_validator("residence_state")
    @classmethod
    def _validate_state(cls, v: str | None) -> str | None:
        if v is None:
            return None
        import re

        v = v.strip().upper()
        if not re.match(STATE_PATTERN, v):
            raise ValueError("Residence state must be a 2-letter code.")
        return v
