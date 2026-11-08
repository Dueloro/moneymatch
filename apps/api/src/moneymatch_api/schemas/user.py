"""User / onboarding schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..constants import REGISTERED_GAMES

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
    dismissed_checklists: list[str]


class LimitsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    daily_loss_cap_cents: int
    daily_entry_cap_cents: int
    daily_deposit_cap_cents: int
    max_concurrent_contests: int
    pending_limits: dict | None
    pending_effective_at: datetime | None
    timeout_until: datetime | None


class GettingStarted(BaseModel):
    """First-match funnel progress — drives the "getting started" checklist that
    nudges a new player from signup to their first wager.
    """

    linked_game: bool
    placed_wager: bool
    complete: bool


class MeResponse(BaseModel):
    """`/me` payload: the user, a computed onboarding flag, and staking limits."""

    user: UserResponse
    needs_onboarding: bool
    limits: LimitsResponse | None = None
    unread_notifications: int = 0
    getting_started: GettingStarted | None = None
    contested_games: list[str] = Field(default_factory=list)


class UpdateMeRequest(BaseModel):
    """Onboarding (username + state + 18+, set once) and/or limit edits."""

    username: str | None = Field(default=None, description="3–20 chars [a-z0-9_]; once")
    residence_state: str | None = Field(default=None, description="2-letter US state")
    dob_attested_18plus: bool | None = None
    daily_loss_cap_cents: int | None = Field(default=None, gt=0)
    daily_entry_cap_cents: int | None = Field(default=None, gt=0)
    daily_deposit_cap_cents: int | None = Field(default=None, gt=0)
    cooloff_days: int | None = Field(default=None, gt=0, le=365)
    dismissed_checklists: list[str] | None = Field(
        default=None,
        description="Catalog game ids whose Play-tab checklist the player dismissed",
    )

    @field_validator("dismissed_checklists")
    @classmethod
    def _validate_catalog_games(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        seen: list[str] = []
        for game in v:
            if game not in REGISTERED_GAMES:
                raise ValueError(f"Unknown game id: {game}")
            if game not in seen:
                seen.append(game)
        return seen

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
