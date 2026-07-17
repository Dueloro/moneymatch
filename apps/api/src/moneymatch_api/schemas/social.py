"""Social wire types — friends (this commit) and challenges (next).

Requests carry **ids or a username/code only** — never amounts or timestamps
(00-README §3). The server owns entry cents, expiry, and match formation.
"""

from __future__ import annotations

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
