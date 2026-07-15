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
    residence_state: str | None
    dob_attested_18plus: bool
    role: str
    status: str
    member_since: datetime


class MeResponse(BaseModel):
    """`/me` payload: the user plus a computed onboarding flag."""

    user: UserResponse
    needs_onboarding: bool


class OnboardingRequest(BaseModel):
    """Onboarding step 2: choose username + residence state + 18+ attestation."""

    username: str = Field(..., description="3–20 chars of [a-z0-9_]; set once")
    residence_state: str = Field(..., description="2-letter US state code")
    dob_attested_18plus: bool

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
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
    def _validate_state(cls, v: str) -> str:
        import re

        v = v.strip().upper()
        if not re.match(STATE_PATTERN, v):
            raise ValueError("Residence state must be a 2-letter code.")
        return v
