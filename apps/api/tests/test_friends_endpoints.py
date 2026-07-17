"""`/friends` HTTP surface: add by username, accept, and the partitioned list
with the caller's own friend code and presence heartbeat."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.user import User

from .conftest import auth_headers, new_sessionmaker

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


async def _onboard(client, auth_id, name):
    await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        await s.commit()
        return user.id


async def test_add_accept_and_list(client):
    await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")

    # alice adds bob by username.
    r = await client.post(
        f"{V1}/friends",
        headers=auth_headers("auth_a"),
        json={"username_or_code": "bob"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["your_friend_code"].startswith("MM-")
    assert [f["username"] for f in body["outgoing"]] == ["bob"]

    # bob sees the incoming request.
    r = await client.get(f"{V1}/friends", headers=auth_headers("auth_b"))
    incoming = r.json()["incoming"]
    assert [f["username"] for f in incoming] == ["alice"]
    friendship_id = incoming[0]["friendship_id"]

    # bob accepts.
    r = await client.post(
        f"{V1}/friends/{friendship_id}/accept", headers=auth_headers("auth_b")
    )
    assert r.status_code == 200
    assert [f["username"] for f in r.json()["friends"]] == ["alice"]

    # alice now shows bob as a friend, and bob is online (just heartbeated).
    r = await client.get(f"{V1}/friends", headers=auth_headers("auth_a"))
    friends = r.json()["friends"]
    assert [f["username"] for f in friends] == ["bob"]
    assert friends[0]["online"] is True


async def test_add_by_friend_code(client):
    await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")
    r = await client.get(f"{V1}/friends", headers=auth_headers("auth_b"))
    bob_code = r.json()["your_friend_code"]

    r = await client.post(
        f"{V1}/friends",
        headers=auth_headers("auth_a"),
        json={"username_or_code": bob_code},
    )
    assert r.status_code == 200
    assert [f["username"] for f in r.json()["outgoing"]] == ["bob"]
