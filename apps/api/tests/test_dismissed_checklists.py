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
        json={"dismissed_checklists": ["cs2.steam"]},
        headers=auth_headers(auth),
    )
    assert r.status_code == 200
    assert r.json()["user"]["dismissed_checklists"] == ["cs2.steam"]
    # Survives a fresh read (server-side, not client state).
    again = await client.get(f"{V1}/me", headers=auth_headers(auth))
    assert again.json()["user"]["dismissed_checklists"] == ["cs2.steam"]


async def test_rejects_unknown_game_id(client):
    auth = "auth_dc_bad"
    await client.get(f"{V1}/me", headers=auth_headers(auth))
    r = await client.patch(
        f"{V1}/me",
        json={"dismissed_checklists": ["not.a.game"]},
        headers=auth_headers(auth),
    )
    assert r.status_code == 422


async def test_removing_active_game_clears_its_dismissal(client):
    """Remove + re-add a game → its checklist comes back (dismissal pruned)."""
    auth = "auth_dc_prune"
    await client.get(f"{V1}/me", headers=auth_headers(auth))
    await client.patch(
        f"{V1}/me",
        json={"active_games": ["chess.lichess", "cs2.steam"]},
        headers=auth_headers(auth),
    )
    await client.patch(
        f"{V1}/me",
        json={"dismissed_checklists": ["cs2.steam"]},
        headers=auth_headers(auth),
    )
    # Remove CS2 from the play set.
    removed = await client.patch(
        f"{V1}/me",
        json={"active_games": ["chess.lichess"]},
        headers=auth_headers(auth),
    )
    assert removed.json()["user"]["dismissed_checklists"] == []

    # Re-add CS2 → still not dismissed, so the checklist shows again.
    readded = await client.patch(
        f"{V1}/me",
        json={"active_games": ["chess.lichess", "cs2.steam"]},
        headers=auth_headers(auth),
    )
    assert "cs2.steam" not in readded.json()["user"]["dismissed_checklists"]
