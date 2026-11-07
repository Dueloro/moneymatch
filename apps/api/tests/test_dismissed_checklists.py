"""Per-game Play-tab checklist dismissals: /me.dismissed_checklists."""

from __future__ import annotations

from .conftest import auth_headers

V1 = "/api/v1"


async def test_fresh_user_has_no_dismissals(client):
    r = await client.get(f"{V1}/me", headers=auth_headers("auth_dc_fresh"))
    assert r.json()["user"]["dismissed_checklists"] == []


async def test_dismiss_persists_on_me(client):
    auth = "auth_dc_set"
    await client.get(f"{V1}/me", headers=auth_headers(auth))
    r = await client.patch(
        f"{V1}/me",
        json={"dismissed_checklists": ["chess.lichess"]},
        headers=auth_headers(auth),
    )
    assert r.status_code == 200
    assert r.json()["user"]["dismissed_checklists"] == ["chess.lichess"]
    # Survives a fresh read (server-side, not client state).
    again = await client.get(f"{V1}/me", headers=auth_headers(auth))
    assert again.json()["user"]["dismissed_checklists"] == ["chess.lichess"]


async def test_rejects_unknown_game_id(client):
    auth = "auth_dc_bad"
    await client.get(f"{V1}/me", headers=auth_headers(auth))
    r = await client.patch(
        f"{V1}/me",
        json={"dismissed_checklists": ["not.a.game"]},
        headers=auth_headers(auth),
    )
    assert r.status_code == 422
