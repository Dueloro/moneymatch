"""`/friends` — the friends list, add-by-username/code, and request lifecycle.

Every GET bumps the caller's presence heartbeat (the design's green dot). Writes
are intents (`{username_or_code}`, a friendship id); the server owns the rest.
No host-game handles are ever exposed here — friendship is a MoneyMatch-only
relation (08-phase-5 · deliverable 2).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..models.user import User
from ..schemas.social import AddFriendRequest, FriendItem, FriendsResponse
from ..services import friends_service

router = APIRouter(prefix="/friends", tags=["friends"])


def _item(row: friends_service.FriendRow) -> FriendItem:
    return FriendItem(
        friendship_id=row.friendship_id,
        user_id=row.user_id,
        username=row.username,
        online=row.online,
    )


async def _view(session: AsyncSession, user: User) -> FriendsResponse:
    view = await friends_service.list_friends(session, user)
    return FriendsResponse(
        your_friend_code=user.friend_code,
        friends=[_item(r) for r in view.friends],
        incoming=[_item(r) for r in view.incoming],
        outgoing=[_item(r) for r in view.outgoing],
    )


@router.get("", response_model=FriendsResponse)
async def list_friends(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> FriendsResponse:
    await friends_service.heartbeat(session, user)
    return await _view(session, user)


@router.post("", response_model=FriendsResponse)
async def add_friend(
    body: AddFriendRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> FriendsResponse:
    await friends_service.add_friend(session, user, body.username_or_code)
    return await _view(session, user)


@router.post("/{friendship_id}/accept", response_model=FriendsResponse)
async def accept_friend(
    friendship_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> FriendsResponse:
    await friends_service.accept_by_id(session, user, friendship_id)
    return await _view(session, user)


@router.post("/{friendship_id}/decline", response_model=FriendsResponse)
async def decline_friend(
    friendship_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> FriendsResponse:
    await friends_service.decline(session, user, friendship_id)
    return await _view(session, user)


@router.post("/{friendship_id}/block", response_model=FriendsResponse)
async def block_friend(
    friendship_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> FriendsResponse:
    await friends_service.block(session, user, friendship_id)
    return await _view(session, user)


@router.delete("/{friendship_id}", response_model=FriendsResponse)
async def remove_friend(
    friendship_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> FriendsResponse:
    await friends_service.remove(session, user, friendship_id)
    return await _view(session, user)
