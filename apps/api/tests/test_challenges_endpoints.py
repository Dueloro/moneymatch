"""`/challenges` HTTP surface: direct challenge → accept forms a PENDING match;
the invite-link flow returns a shareable path with a public preview; and
rematch re-challenges the same opponent (08-phase-5 · deliverables 3, 6)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.user import User

from .conftest import auth_headers, new_sessionmaker
from .factories import create_linked_account

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"
CS2 = "cs2.faceit"


async def _onboard(client, auth_id, name, *, link=True):
    await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        if link:
            await create_linked_account(s, user, CS2, host_account_id=f"host_{name}")
        await s.commit()
        return user.id


async def _befriend(client, a_auth, b_auth):
    r = await client.get(f"{V1}/friends", headers=auth_headers(b_auth))
    # a adds b, b accepts.
    await client.post(
        f"{V1}/friends",
        headers=auth_headers(a_auth),
        json={"username_or_code": "bob"},
    )
    r = await client.get(f"{V1}/friends", headers=auth_headers(b_auth))
    fid = r.json()["incoming"][0]["friendship_id"]
    await client.post(f"{V1}/friends/{fid}/accept", headers=auth_headers(b_auth))


async def test_direct_challenge_and_accept(client):
    await _onboard(client, "auth_a", "alice")
    b_id = await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b")

    r = await client.post(
        f"{V1}/challenges",
        headers=auth_headers("auth_a"),
        json={
            "challengee_id": str(b_id),
            "game": CS2,
            "market": "kd_ratio",
            "entry_preset_cents": 1000,
        },
    )
    assert r.status_code == 200, r.text
    challenge_id = r.json()["challenge"]["id"]
    assert r.json()["challenge"]["state"] == "sent"

    # bob accepts → gets a match id, and the match is his to confirm.
    r = await client.post(
        f"{V1}/challenges/{challenge_id}/accept", headers=auth_headers("auth_b")
    )
    assert r.status_code == 200, r.text
    match_id = r.json()["match_id"]
    r = await client.get(
        f"{V1}/play/matches/{match_id}", headers=auth_headers("auth_b")
    )
    assert r.status_code == 200
    assert r.json()["state"] == "PENDING"


async def test_invite_link_preview_is_public_and_acceptable(client):
    await _onboard(client, "auth_a", "alice")

    r = await client.post(
        f"{V1}/challenges",
        headers=auth_headers("auth_a"),
        json={"game": CS2, "market": "kd_ratio", "entry_preset_cents": 1000},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    token = body["invite_token"]
    assert body["invite_path"] == f"/i/{token}"

    # Public preview: no auth header.
    r = await client.get(f"{V1}/challenges/token/{token}")
    assert r.status_code == 200
    assert r.json()["challenger_username"] == "alice"
    assert r.json()["valid"] is True

    # A fresh, linked user accepts the invite.
    await _onboard(client, "auth_c", "carol")
    r = await client.post(
        f"{V1}/challenges/token/{token}/accept", headers=auth_headers("auth_c")
    )
    assert r.status_code == 200, r.text
    assert "match_id" in r.json()


async def test_rematch_recreates_challenge(client):
    await _onboard(client, "auth_a", "alice")
    b_id = await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b")

    # First contest via a direct challenge → accept.
    r = await client.post(
        f"{V1}/challenges",
        headers=auth_headers("auth_a"),
        json={
            "challengee_id": str(b_id),
            "game": CS2,
            "market": "kd_ratio",
            "entry_preset_cents": 1000,
        },
    )
    challenge_id = r.json()["challenge"]["id"]
    r = await client.post(
        f"{V1}/challenges/{challenge_id}/accept", headers=auth_headers("auth_b")
    )
    match_id = r.json()["match_id"]

    # Rematch: one field, same opponent/market/entry.
    r = await client.post(
        f"{V1}/challenges",
        headers=auth_headers("auth_a"),
        json={"rematch_of": match_id},
    )
    assert r.status_code == 200, r.text
    ch = r.json()["challenge"]
    assert ch["challengee_id"] == str(b_id)
    assert ch["market"] == "kd_ratio"
    assert ch["entry_cents"] == 1000
