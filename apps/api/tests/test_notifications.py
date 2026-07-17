"""Notifications (08-phase-5 · tests): unread counts and idempotent mark-read,
at the service level and over the HTTP Inbox surface."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.user import User
from moneymatch_api.services import notifications_service as notes

from .conftest import auth_headers, new_sessionmaker
from .factories import create_user

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


async def test_unread_count_and_mark_read_idempotent(session):
    user = await create_user(session, username="alice")
    a = await notes.emit(session, user.id, "friend_request", {"n": 1})
    await notes.emit(session, user.id, "challenge_received", {"n": 2})
    await notes.emit(session, user.id, "settled", {"n": 3})

    assert await notes.unread_count(session, user.id) == 3

    # Mark one read → 2 left.
    unread = await notes.mark_read(session, user.id, ids=[a.id])
    assert unread == 2
    # Re-marking the same one is a no-op.
    assert await notes.mark_read(session, user.id, ids=[a.id]) == 2

    # Mark all read → 0, and again is idempotent.
    assert await notes.mark_read(session, user.id) == 0
    assert await notes.mark_read(session, user.id) == 0


async def test_list_newest_first(session):
    user = await create_user(session, username="alice")
    for i in range(3):
        await notes.emit(session, user.id, "system", {"i": i})
    rows = await notes.list_for_user(session, user.id)
    assert [r.payload["i"] for r in rows] == [2, 1, 0]


async def test_inbox_endpoint_and_me_bell(client):
    await client.get(f"{V1}/me", headers=auth_headers("auth_a"))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == "auth_a"))
        user.username = "alice"
        await notes.emit(s, user.id, "settled", {"x": 1})
        await notes.emit(s, user.id, "friend_request", {"x": 2})
        await s.commit()

    # /me carries the unread count for the sidebar bell.
    r = await client.get(f"{V1}/me", headers=auth_headers("auth_a"))
    assert r.json()["unread_notifications"] == 2

    # Inbox lists them, then marking read clears the bell.
    r = await client.get(f"{V1}/notifications", headers=auth_headers("auth_a"))
    body = r.json()
    assert body["unread"] == 2 and len(body["items"]) == 2

    r = await client.post(
        f"{V1}/notifications/read", headers=auth_headers("auth_a"), json={}
    )
    assert r.json()["unread"] == 0
    r = await client.get(f"{V1}/me", headers=auth_headers("auth_a"))
    assert r.json()["unread_notifications"] == 0
