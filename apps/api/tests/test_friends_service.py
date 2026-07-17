"""Friendship state machine (08-phase-5 · tests): duplicate requests, blocked
users, self-add rejected, the mirror-accept shortcut, caps, and presence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from moneymatch_api.errors import APIError
from moneymatch_api.models.social import Friendship
from moneymatch_api.services import friends_service

from .factories import create_user

pytestmark = pytest.mark.asyncio


async def test_add_by_username_creates_pending(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")

    fr = await friends_service.add_friend(session, a, "bob")

    assert fr.state == "pending"
    assert fr.user_id == a.id and fr.friend_id == b.id


async def test_add_by_friend_code(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")

    fr = await friends_service.add_friend(session, a, b.friend_code.lower())

    assert fr.friend_id == b.id


async def test_self_add_rejected(session):
    a = await create_user(session, username="alice")
    with pytest.raises(APIError) as exc:
        await friends_service.add_friend(session, a, "alice")
    assert exc.value.code == "self_add"


async def test_unknown_user_rejected(session):
    a = await create_user(session, username="alice")
    with pytest.raises(APIError) as exc:
        await friends_service.add_friend(session, a, "nobody")
    assert exc.value.code == "user_not_found"


async def test_duplicate_request_rejected(session):
    a = await create_user(session, username="alice")
    await create_user(session, username="bob")
    await friends_service.add_friend(session, a, "bob")
    with pytest.raises(APIError) as exc:
        await friends_service.add_friend(session, a, "bob")
    assert exc.value.code == "request_pending"


async def test_mirror_request_auto_accepts(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    await friends_service.add_friend(session, a, "bob")

    # bob adding alice back mirrors the pending request → accepted.
    fr = await friends_service.add_friend(session, b, "alice")
    assert fr.state == "accepted"
    assert fr.accepted_at is not None


async def test_accept_only_by_addressee(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    fr = await friends_service.add_friend(session, a, "bob")

    # The requester can't accept their own request.
    with pytest.raises(APIError) as exc:
        await friends_service.accept_by_id(session, a, fr.id)
    assert exc.value.code == "not_addressee"

    accepted = await friends_service.accept_by_id(session, b, fr.id)
    assert accepted.state == "accepted"


async def test_add_when_already_friends_rejected(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    fr = await friends_service.add_friend(session, a, "bob")
    await friends_service.accept_by_id(session, b, fr.id)

    with pytest.raises(APIError) as exc:
        await friends_service.add_friend(session, a, "bob")
    assert exc.value.code == "already_friends"


async def test_blocked_relationship_blocks_readd(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    fr = await friends_service.add_friend(session, a, "bob")
    await friends_service.block(session, a, fr.id)

    # Neither party can re-add while blocked.
    with pytest.raises(APIError) as exc:
        await friends_service.add_friend(session, b, "alice")
    assert exc.value.code == "blocked"


async def test_decline_removes_row_and_allows_readd(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    fr = await friends_service.add_friend(session, a, "bob")
    await friends_service.decline(session, b, fr.id)

    # Fresh request is allowed after a decline.
    fr2 = await friends_service.add_friend(session, a, "bob")
    assert fr2.state == "pending"


async def test_pending_outbound_cap(session, monkeypatch):
    monkeypatch.setattr(friends_service, "MAX_PENDING_OUTBOUND", 1)
    a = await create_user(session, username="alice")
    await create_user(session, username="bob")
    await create_user(session, username="carol")
    await friends_service.add_friend(session, a, "bob")
    with pytest.raises(APIError) as exc:
        await friends_service.add_friend(session, a, "carol")
    assert exc.value.code == "pending_cap"


async def test_list_partitions_and_presence(session):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    await create_user(session, username="carol")
    d = await create_user(session, username="dave")

    # a↔b accepted (b online), a→c pending outbound, d→a pending incoming.
    fr_ab = await friends_service.add_friend(session, a, "bob")
    await friends_service.accept_by_id(session, b, fr_ab.id)
    b.last_seen_at = datetime.now(UTC)
    await friends_service.add_friend(session, a, "carol")
    await friends_service.add_friend(session, d, "alice")
    await session.flush()

    view = await friends_service.list_friends(session, a)
    assert [f.username for f in view.friends] == ["bob"]
    assert view.friends[0].online is True
    assert [f.username for f in view.outgoing] == ["carol"]
    assert [f.username for f in view.incoming] == ["dave"]


async def test_presence_window():
    now = datetime.now(UTC)
    assert friends_service.is_online(now, now=now) is True
    assert friends_service.is_online(now - timedelta(minutes=10), now=now) is False
    assert friends_service.is_online(None) is False


async def test_reverse_pair_unique_guard(session):
    """A→B pending then B→A (non-mirror path already covered); ensure the DB
    never holds two rows for the same pair."""
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    fr = await friends_service.add_friend(session, a, "bob")
    await friends_service.accept_by_id(session, b, fr.id)

    from sqlalchemy import func, or_, select

    count = await session.scalar(
        select(func.count())
        .select_from(Friendship)
        .where(or_(Friendship.user_id == a.id, Friendship.friend_id == a.id))
    )
    assert count == 1
