"""`/inbox` — the Social badge counts only what arrived since the inbox was last seen;
per-item read state is untouched.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.user import User
from moneymatch_api.services import notifications_service as notes

from .conftest import auth_headers, new_sessionmaker
from .test_chat import _befriend, _onboard

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


async def _badge(client, auth: str) -> int:
    r = await client.get(f"{V1}/inbox/badge", headers=auth_headers(auth))
    assert r.status_code == 200, r.text
    return r.json()["badge"]


async def _dm(client, sender: str, peer_id: str, text: str) -> str:
    r = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers(sender),
        json={"kind": "dm", "user_id": peer_id},
    )
    conversation_id = r.json()["id"]
    r = await client.post(
        f"{V1}/chat/conversations/{conversation_id}/messages",
        headers=auth_headers(sender),
        json={"body": text},
    )
    assert r.status_code == 200, r.text
    return conversation_id


async def _notify(auth: str, kind: str = "settled") -> None:
    async with new_sessionmaker()() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth))
        await notes.emit(s, user.id, kind, {})
        await s.commit()


async def test_seen_clears_badge_but_not_item_unread(client):
    alice = await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b", "bob")
    await client.post(
        f"{V1}/notifications/read", headers=auth_headers("auth_a"), json={}
    )
    conversation_id = await _dm(client, "auth_b", alice, "gg?")
    await _notify("auth_a")

    assert await _badge(client, "auth_a") == 2

    r = await client.post(f"{V1}/inbox/seen", headers=auth_headers("auth_a"))
    assert r.status_code == 200 and r.json()["badge"] == 0
    assert await _badge(client, "auth_a") == 0

    async with new_sessionmaker()() as s:
        user = await s.scalar(select(User).where(User.auth_id == "auth_a"))
        assert user.inbox_seen_at is not None

    chats = (
        await client.get(f"{V1}/chat/conversations", headers=auth_headers("auth_a"))
    ).json()
    row = next(c for c in chats["conversations"] if c["id"] == conversation_id)
    assert row["unread"] == 1 and chats["unread_total"] == 1
    feed = (
        await client.get(f"{V1}/notifications", headers=auth_headers("auth_a"))
    ).json()
    assert feed["unread"] == 1


async def test_new_items_after_seen_rebadge(client):
    alice = await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b", "bob")
    await _dm(client, "auth_b", alice, "first")
    await client.post(f"{V1}/inbox/seen", headers=auth_headers("auth_a"))
    assert await _badge(client, "auth_a") == 0

    await _dm(client, "auth_b", alice, "second")
    await _notify("auth_a")
    assert await _badge(client, "auth_a") == 2


async def test_badge_ignores_items_already_read(client):
    alice = await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b", "bob")
    conversation_id = await _dm(client, "auth_b", alice, "hi")
    await client.post(
        f"{V1}/chat/conversations/{conversation_id}/read",
        headers=auth_headers("auth_a"),
    )
    await client.post(
        f"{V1}/notifications/read", headers=auth_headers("auth_a"), json={}
    )
    assert await _badge(client, "auth_a") == 0


async def test_never_seen_badge_is_the_unread_total(client):
    alice = await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b", "bob")
    await _dm(client, "auth_b", alice, "yo")
    feed = (
        await client.get(f"{V1}/notifications", headers=auth_headers("auth_a"))
    ).json()
    assert await _badge(client, "auth_a") == 1 + feed["unread"]
