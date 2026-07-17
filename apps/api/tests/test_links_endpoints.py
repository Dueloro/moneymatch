"""/links endpoints — link/refresh/unlink flow, conflicts, and flag blocking.

Host APIs are respx-mocked (no live network). Covers the phase's required
linking tests: unknown → 404, already-bound host → 409, second game independent,
snapshot refresh, disabled-flag BLOCKED, and admin-only unlink.
"""

from __future__ import annotations

import httpx
import respx
from sqlalchemy import text

from .conftest import auth_headers

CHESS = "chess.lichess"
DOTA = "dota2.opendota"
LI = "https://lichess.org/api/user"
OD = "https://api.opendota.com/api"


def _lichess_user(username="magnus", rating=2800):
    return {
        "id": username.lower(),
        "username": username,
        "url": f"https://lichess.org/@/{username}",
        "createdAt": 1_300_000_000_000,
        "perfs": {"blitz": {"rating": rating, "games": 500}},
        "count": {"rated": 500, "win": 300, "draw": 50, "loss": 150},
    }


def _mock_dota(account_id="70388657"):
    respx.get(f"{OD}/players/{account_id}").mock(
        return_value=httpx.Response(
            200, json={"profile": {"personaname": "hero"}, "rank_tier": 55}
        )
    )
    respx.get(f"{OD}/players/{account_id}/wl").mock(
        return_value=httpx.Response(200, json={"win": 30, "lose": 20})
    )
    respx.get(f"{OD}/players/{account_id}/recentMatches").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "match_id": i,
                    "player_slot": 1,
                    "radiant_win": True,
                    "start_time": 1_700_000_000 + i,
                    "kills": 10,
                    "deaths": 4,
                    "assists": 8,
                    "gold_per_min": 500 + i,
                }
                for i in range(3)
            ],
        )
    )


def _game(resp, game):
    return next(g for g in resp["games"] if g["game"] == game)


@respx.mock
async def test_link_lichess_success(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("u-chess"),
    )
    assert r.status_code == 200, r.text
    chess = _game(r.json(), CHESS)
    assert chess["status"] == "LINKED"
    assert chess["host_username"] == "magnus"
    # Chess ratings live per time-control in `formats` (generic `rating` is FPS).
    assert chess["profile"]["primary_speed"] == "blitz"
    assert chess["profile"]["formats"][0]["rating"] == 2800

    # GET reflects the binding.
    g = await client.get("/api/v1/links", headers=auth_headers("u-chess"))
    assert _game(g.json(), CHESS)["status"] == "LINKED"


@respx.mock
async def test_unknown_username_is_404(client):
    respx.get(f"{LI}/ghost").mock(return_value=httpx.Response(404))
    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "ghost"},
        headers=auth_headers("u-ghost"),
    )
    assert r.status_code == 404
    assert r.json()["code"] == "host_account_unlinkable"


@respx.mock
async def test_second_user_cannot_bind_bound_account(client):
    respx.get(url__regex=r"https://lichess\.org/api/user/[Mm]agnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    ok = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("first"),
    )
    assert ok.status_code == 200
    clash = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "Magnus"},  # case variant, same account
        headers=auth_headers("second"),
    )
    assert clash.status_code == 409
    assert clash.json()["code"] == "account_already_bound"


@respx.mock
async def test_relinking_same_game_conflicts(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    respx.get(f"{LI}/hikaru").mock(
        return_value=httpx.Response(200, json=_lichess_user("hikaru"))
    )
    await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("dup"),
    )
    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "hikaru"},
        headers=auth_headers("dup"),
    )
    assert r.status_code == 409 and r.json()["code"] == "already_linked"


@respx.mock
async def test_second_game_links_independently(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    _mock_dota()
    await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("multi"),
    )
    r = await client.post(
        "/api/v1/links",
        json={"game": DOTA, "username": "70388657"},
        headers=auth_headers("multi"),
    )
    assert r.status_code == 200
    body = r.json()
    assert _game(body, CHESS)["status"] == "LINKED"
    assert _game(body, DOTA)["status"] == "LINKED"


@respx.mock
async def test_refresh_updates_snapshot(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user(rating=2800))
    )
    await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("refresh"),
    )
    # Rating changes upstream; refresh should pick it up.
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user(rating=2850))
    )
    r = await client.get(
        f"/api/v1/links/{CHESS}/profile", headers=auth_headers("refresh")
    )
    assert r.status_code == 200
    assert _game(r.json(), CHESS)["profile"]["formats"][0]["rating"] == 2850


async def test_disabled_flag_blocks_and_marks_blocked(client, session):
    await session.execute(
        text("UPDATE feature_flags SET enabled = false WHERE key = :k"),
        {"k": f"game:{CHESS}"},
    )
    await session.commit()

    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("blocked"),
    )
    assert r.status_code == 409 and r.json()["code"] == "game_disabled"

    g = await client.get("/api/v1/links", headers=auth_headers("blocked"))
    assert _game(g.json(), CHESS)["status"] == "BLOCKED"


@respx.mock
async def test_unlink_requires_admin(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("noadmin"),
    )
    r = await client.request(
        "DELETE", f"/api/v1/links/{CHESS}", headers=auth_headers("noadmin")
    )
    assert r.status_code == 403 and r.json()["code"] == "admin_only"
