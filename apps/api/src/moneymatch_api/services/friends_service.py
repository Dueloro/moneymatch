"""Friends — the request/accept/decline/block state machine + presence-lite.

Adds by MoneyMatch **username** (exact citext match — never host-game accounts,
so linkage never leaks) or by immutable **friend code** (`MM-7F3K2Q`). One row
per relationship (`user_id` = requester, `friend_id` = addressee); the service
guards the reverse pair so A→B and B→A never coexist — a request that mirrors a
pending one auto-accepts. Caps bite here (500 friends, 20 pending outbound). No
chat at MVP (08-phase-5 · deliverable 2). Flushes, never commits — the caller
owns the transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    MAX_FRIENDS,
    MAX_PENDING_OUTBOUND,
    PRESENCE_WINDOW_SECONDS,
)
from ..errors import APIError
from ..models.social import Friendship
from ..models.user import User
from . import notifications_service


class FriendError(APIError):
    """A friendship-transition failure (RFC-7807 via APIError)."""


def _now() -> datetime:
    return datetime.now(UTC)


def is_online(last_seen_at: datetime | None, *, now: datetime | None = None) -> bool:
    if last_seen_at is None:
        return False
    now = now or _now()
    return (now - last_seen_at).total_seconds() <= PRESENCE_WINDOW_SECONDS


async def heartbeat(session: AsyncSession, user: User) -> None:
    """Bump the presence heartbeat (called from polled social surfaces)."""
    user.last_seen_at = _now()
    await session.flush()


# --------------------------------------------------------------------------- #
# Lookups.
# --------------------------------------------------------------------------- #


async def resolve_target(session: AsyncSession, query: str) -> User:
    """Resolve `username_or_code` to a user — friend code if it looks like one,
    otherwise an exact username match. Never resolves host-game handles."""
    q = query.strip()
    if not q:
        raise FriendError(
            "empty_query", "Enter a username or friend code.", status_code=422
        )
    if q.upper().startswith("MM-"):
        target = await session.scalar(select(User).where(User.friend_code == q.upper()))
    else:
        target = await session.scalar(select(User).where(User.username == q))
    if target is None:
        raise FriendError(
            "user_not_found", "No player with that username or code.", status_code=404
        )
    return target


async def _relationship(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> Friendship | None:
    """The friendship row between two users in either direction, if any."""
    return await session.scalar(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == a, Friendship.friend_id == b),
                and_(Friendship.user_id == b, Friendship.friend_id == a),
            )
        )
    )


async def are_friends(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    """Whether two users are accepted friends (either direction)."""
    rel = await _relationship(session, a, b)
    return rel is not None and rel.state == "accepted"


async def _accepted_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Friendship)
            .where(
                Friendship.state == "accepted",
                or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
            )
        )
        or 0
    )


async def _pending_outbound_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Friendship)
            .where(Friendship.user_id == user_id, Friendship.state == "pending")
        )
        or 0
    )


# --------------------------------------------------------------------------- #
# Transitions.
# --------------------------------------------------------------------------- #


async def add_friend(session: AsyncSession, user: User, query: str) -> Friendship:
    """Send a friend request (or auto-accept a mirrored pending one)."""
    target = await resolve_target(session, query)
    if target.id == user.id:
        raise FriendError("self_add", "You can't add yourself.", status_code=422)

    existing = await _relationship(session, user.id, target.id)
    if existing is not None:
        if existing.state == "accepted":
            raise FriendError(
                "already_friends", "You're already friends.", status_code=409
            )
        if existing.state == "blocked":
            raise FriendError(
                "blocked", "This relationship is blocked.", status_code=403
            )
        # pending: mirror → accept; same direction → duplicate.
        if existing.friend_id == user.id:
            return await accept(session, user, existing)
        raise FriendError(
            "request_pending", "A request is already pending.", status_code=409
        )

    if await _accepted_count(session, user.id) >= MAX_FRIENDS:
        raise FriendError(
            "friend_cap", "You've hit the friends limit.", status_code=409
        )
    if await _pending_outbound_count(session, user.id) >= MAX_PENDING_OUTBOUND:
        raise FriendError(
            "pending_cap",
            "Too many pending requests — wait for replies.",
            status_code=409,
        )

    friendship = Friendship(user_id=user.id, friend_id=target.id, state="pending")
    session.add(friendship)
    await session.flush()
    await notifications_service.emit(
        session,
        target.id,
        "friend_request",
        {
            "friendship_id": str(friendship.id),
            "from_user_id": str(user.id),
            "from_username": user.username,
            "status": "received",
        },
    )
    return friendship


async def _load_membership(
    session: AsyncSession, user: User, friendship_id: uuid.UUID
) -> Friendship:
    friendship = await session.get(Friendship, friendship_id)
    if friendship is None or user.id not in (friendship.user_id, friendship.friend_id):
        raise FriendError(
            "friendship_not_found", "No such friend request.", status_code=404
        )
    return friendship


async def accept(
    session: AsyncSession, user: User, friendship: Friendship
) -> Friendship:
    """Accept a pending request — only the addressee may accept."""
    if friendship.state != "pending":
        raise FriendError(
            "not_pending", "This request can't be accepted.", status_code=409
        )
    if friendship.friend_id != user.id:
        raise FriendError(
            "not_addressee", "Only the recipient can accept.", status_code=403
        )
    friendship.state = "accepted"
    friendship.accepted_at = _now()
    await session.flush()
    await notifications_service.emit(
        session,
        friendship.user_id,
        "friend_request",
        {
            "friendship_id": str(friendship.id),
            "from_user_id": str(user.id),
            "from_username": user.username,
            "status": "accepted",
        },
    )
    return friendship


async def accept_by_id(
    session: AsyncSession, user: User, friendship_id: uuid.UUID
) -> Friendship:
    return await accept(
        session, user, await _load_membership(session, user, friendship_id)
    )


async def decline(session: AsyncSession, user: User, friendship_id: uuid.UUID) -> None:
    """Decline a pending request (addressee) — the row is removed so a fresh
    request can be sent later. Declining a non-pending row is rejected."""
    friendship = await _load_membership(session, user, friendship_id)
    if friendship.state != "pending":
        raise FriendError(
            "not_pending", "This request can't be declined.", status_code=409
        )
    if friendship.friend_id != user.id:
        raise FriendError(
            "not_addressee", "Only the recipient can decline.", status_code=403
        )
    await session.delete(friendship)
    await session.flush()


async def remove(session: AsyncSession, user: User, friendship_id: uuid.UUID) -> None:
    """Unfriend / cancel an outbound request — either party may remove."""
    friendship = await _load_membership(session, user, friendship_id)
    if friendship.state == "blocked":
        raise FriendError("blocked", "Unblock before removing.", status_code=409)
    await session.delete(friendship)
    await session.flush()


async def block(
    session: AsyncSession, user: User, friendship_id: uuid.UUID
) -> Friendship:
    """Block the other party — either side may block; freezes the relationship."""
    friendship = await _load_membership(session, user, friendship_id)
    friendship.state = "blocked"
    friendship.blocked_by = user.id
    friendship.accepted_at = None
    await session.flush()
    return friendship


# --------------------------------------------------------------------------- #
# Listing (accepted friends + presence, plus pending in/out).
# --------------------------------------------------------------------------- #


@dataclass
class FriendRow:
    friendship_id: uuid.UUID
    user_id: uuid.UUID
    username: str | None
    online: bool


@dataclass
class FriendsView:
    friends: list[FriendRow]
    incoming: list[FriendRow]
    outgoing: list[FriendRow]


async def list_friends(session: AsyncSession, user: User) -> FriendsView:
    """Accepted friends (with presence) plus incoming/outgoing pending requests.
    Blocked relationships are hidden."""
    now = _now()
    rows = list(
        await session.scalars(
            select(Friendship).where(
                Friendship.state.in_(("accepted", "pending")),
                or_(Friendship.user_id == user.id, Friendship.friend_id == user.id),
            )
        )
    )
    other_ids = [f.friend_id if f.user_id == user.id else f.user_id for f in rows]
    profiles: dict[uuid.UUID, User] = {}
    if other_ids:
        for u in await session.scalars(select(User).where(User.id.in_(other_ids))):
            profiles[u.id] = u

    friends: list[FriendRow] = []
    incoming: list[FriendRow] = []
    outgoing: list[FriendRow] = []
    for f in rows:
        other_id = f.friend_id if f.user_id == user.id else f.user_id
        other = profiles.get(other_id)
        row = FriendRow(
            friendship_id=f.id,
            user_id=other_id,
            username=other.username if other else None,
            online=is_online(other.last_seen_at if other else None, now=now),
        )
        if f.state == "accepted":
            friends.append(row)
        elif f.friend_id == user.id:
            incoming.append(row)
        else:
            outgoing.append(row)
    friends.sort(key=lambda r: (not r.online, (r.username or "").lower()))
    return FriendsView(friends=friends, incoming=incoming, outgoing=outgoing)
