"""Social wire types — friends and challenges (+ invite links). The server owns entry
cents, expiry, and match formation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FriendItem(BaseModel):
    """One person in the friends list or a pending request."""

    friendship_id: UUID
    user_id: UUID
    username: str | None
    online: bool


class FriendsResponse(BaseModel):
    your_friend_code: str
    friends: list[FriendItem]
    incoming: list[FriendItem]
    outgoing: list[FriendItem]


class AddFriendRequest(BaseModel):
    """Add by exact MoneyMatch username or immutable friend code (`MM-7F3K2Q`)."""

    username_or_code: str


class CreateChallengeRequest(BaseModel):
    challengee_id: UUID | None = None
    rematch_of: UUID | None = None
    game: str | None = None
    market: str | None = None
    speed: str | None = None
    entry_preset_cents: int | None = None


class ChallengeView(BaseModel):
    """A challenge as a party sees it (the Respond slip / sent list)."""

    id: UUID
    challenger_id: UUID
    challenger_username: str | None
    challengee_id: UUID | None
    game: str
    market: str
    market_label: str
    kind: str
    speed: str | None
    entry_cents: int
    friendly: bool
    state: str
    match_id: UUID | None
    is_invite: bool
    expires_at: datetime


class ChallengeCreatedResponse(BaseModel):
    """The created challenge, plus the shareable path for invite links."""

    challenge: ChallengeView
    invite_token: str | None = None
    invite_path: str | None = None


class ChallengeAcceptResponse(BaseModel):
    """Accepting forms a PENDING match; the client navigates to it to confirm."""

    match_id: UUID


class ChallengePreviewResponse(BaseModel):
    """Public invite-link preview (no auth) — market, entry, challenger name."""

    game: str
    market: str
    market_label: str
    kind: str
    speed: str | None
    entry_cents: int
    challenger_username: str | None
    state: str
    valid: bool
    expires_at: datetime
