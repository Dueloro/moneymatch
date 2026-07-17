"""Social wire types — friends and challenges (+ invite links).

Requests carry **ids or a username/code only** — never amounts or timestamps
(00-README §3). The server owns entry cents, expiry, and match formation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# --- friends -------------------------------------------------------------- #


class FriendItem(BaseModel):
    """One person in the friends list or a pending request (design PDF p.8)."""

    friendship_id: UUID
    user_id: UUID
    username: str | None
    online: bool  # green dot: heartbeat within the presence window


class FriendsResponse(BaseModel):
    your_friend_code: str  # shown on Profile / the add-friends input hint
    friends: list[FriendItem]
    incoming: list[FriendItem]  # requests awaiting your accept/decline
    outgoing: list[FriendItem]  # your sent requests awaiting their reply


class AddFriendRequest(BaseModel):
    """Add by exact MoneyMatch username or immutable friend code (`MM-7F3K2Q`)."""

    username_or_code: str


# --- challenges ----------------------------------------------------------- #


class CreateChallengeRequest(BaseModel):
    """One shape for all three flows (the server picks based on which fields are
    set): direct (`challengee_id`), rematch (`rematch_of`), or invite link
    (neither). game/market/entry are ignored for a rematch (copied from the
    original match). Entry is a preset choice — the server owns the cents."""

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
    invite_path: str | None = None  # e.g. /i/{token}


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
    valid: bool  # still open + unexpired → acceptable
    expires_at: datetime
