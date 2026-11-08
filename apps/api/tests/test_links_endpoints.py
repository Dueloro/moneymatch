"""/links endpoints — link/refresh/unlink flow, conflicts, and flag blocking.

Typed-username linking (`POST /links`) is only open under E2E auth, so these tests run
with it enabled; the OAuth path is covered in `test_lichess_oauth`.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import text

from .conftest import auth_headers

CHESS = "chess.lichess"
LI = "https://lichess.org/api/user"


@pytest.fixture(autouse=True)
def _e2e_auth(app, monkeypatch) -> None:
    settings = app.state.settings.model_copy(update={"e2e_auth_enabled": True})
    monkeypatch.setattr(app.state, "settings", settings)


def _lichess_user(username="magnus", rating=2800):
    return {
        "id": username.lower(),
        "username": username,
        "url": f"https://lichess.org/@/{username}",
        "createdAt": 1_300_000_000_000,
        "perfs": {"blitz": {"rating": rating, "games": 500}},
        "count": {"rated": 500, "win": 300, "draw": 50, "loss": 150},
    }


def _lichess_games(ndjson: str = "") -> None:
    respx.get(url__regex=r"https://lichess\.org/api/games/user/.*").mock(
        return_value=httpx.Response(200, text=ndjson)
    )


def _game(resp, game):
    return next(g for g in resp["games"] if g["game"] == game)


@respx.mock
async def test_link_lichess_success(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    _lichess_games()
    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("u-chess"),
    )
    assert r.status_code == 200, r.text
    chess = _game(r.json(), CHESS)
    assert chess["status"] == "LINKED"
    assert chess["host_username"] == "magnus"
    assert chess["profile"]["primary_speed"] == "blitz"
    assert chess["profile"]["formats"][0]["rating"] == 2800

    g = await client.get("/api/v1/links", headers=auth_headers("u-chess"))
    assert _game(g.json(), CHESS)["status"] == "LINKED"


@respx.mock
async def test_unknown_username_is_404(client):
    respx.get(f"{LI}/ghost").mock(return_value=httpx.Response(404))
    _lichess_games()
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
    _lichess_games()
    ok = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("first"),
    )
    assert ok.status_code == 200
    clash = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "Magnus"},
        headers=auth_headers("second"),
    )
    assert clash.status_code == 409
    assert clash.json()["code"] == "account_already_bound"


@respx.mock
async def test_relinking_same_game_conflicts(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user())
    )
    _lichess_games()
    respx.get(f"{LI}/hikaru").mock(
        return_value=httpx.Response(200, json=_lichess_user("hikaru"))
    )
    _lichess_games()
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
async def test_refresh_updates_snapshot(client):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user(rating=2800))
    )
    _lichess_games()
    await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("refresh"),
    )
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user(rating=2850))
    )
    _lichess_games()
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
    _lichess_games()
    await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("noadmin"),
    )
    r = await client.request(
        "DELETE", f"/api/v1/links/{CHESS}", headers=auth_headers("noadmin")
    )
    assert r.status_code == 403 and r.json()["code"] == "admin_only"
