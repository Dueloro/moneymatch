"""Ownership-verified Lichess linking via OAuth (PKCE)."""

from __future__ import annotations

import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from sqlalchemy import select, text

from moneymatch_api.clock import now
from moneymatch_api.models.lichess_oauth import LichessOAuthState
from moneymatch_api.models.linked_account import LinkedAccount

from .conftest import auth_headers

CHESS = "chess.lichess"
START = "/api/v1/links/lichess/oauth/start"
CALLBACK = "/api/v1/links/lichess/oauth/callback"
TOKEN = "https://lichess.org/api/token"
ACCOUNT = "https://lichess.org/api/account"


def _user(username="Magnus", rating=2800):
    return {
        "id": username.lower(),
        "username": username,
        "url": f"https://lichess.org/@/{username}",
        "createdAt": 1_300_000_000_000,
        "perfs": {"blitz": {"rating": rating, "games": 500}},
        "count": {"rated": 500, "win": 300, "draw": 50, "loss": 150},
    }


def _mock_lichess(username="Magnus", *, token_status=200):
    token = respx.post(TOKEN).mock(
        return_value=httpx.Response(
            token_status,
            json=(
                {"token_type": "Bearer", "access_token": "lio_tok", "expires_in": 1}
                if token_status == 200
                else {"error": "invalid_grant"}
            ),
        )
    )
    account = respx.get(ACCOUNT).mock(
        return_value=httpx.Response(200, json=_user(username))
    )
    revoke = respx.delete(TOKEN).mock(return_value=httpx.Response(204))
    respx.get(url__regex=r"https://lichess\.org/api/user/.*").mock(
        return_value=httpx.Response(200, json=_user(username))
    )
    respx.get(url__regex=r"https://lichess\.org/api/games/user/.*").mock(
        return_value=httpx.Response(200, text="")
    )
    return token, account, revoke


async def _start(client, sub: str) -> dict[str, str]:
    r = await client.post(START, headers=auth_headers(sub))
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["authorize_url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://lichess.org/oauth"
    return {k: v[0] for k, v in parse_qs(url.query).items()}


async def test_start_builds_pkce_authorize_url(client, session):
    q = await _start(client, "o-start")
    assert q["response_type"] == "code"
    assert q["client_id"] == "moneymatch"
    assert q["redirect_uri"] == "http://localhost:5173/link/lichess/callback"
    assert q["code_challenge_method"] == "S256"
    assert "scope" not in q

    row = await session.get(LichessOAuthState, q["state"])
    assert row is not None
    digest = hashlib.sha256(row.code_verifier.encode()).digest()
    assert q["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert row.code_verifier not in str(q)
    assert row.expires_at > now() + timedelta(minutes=9)


async def test_start_requires_auth(client):
    r = await client.post(START)
    assert r.status_code == 401


@respx.mock
async def test_callback_links_confirmed_account_and_revokes(client, session):
    q = await _start(client, "o-ok")
    token, account, revoke = _mock_lichess("Magnus")

    r = await client.post(
        CALLBACK,
        json={"code": "liu_code", "state": q["state"]},
        headers=auth_headers("o-ok"),
    )
    assert r.status_code == 200, r.text
    chess = next(g for g in r.json()["games"] if g["game"] == CHESS)
    assert chess["status"] == "LINKED"
    assert chess["host_username"] == "Magnus"

    form = parse_qs(token.calls.last.request.content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["liu_code"]
    assert form["redirect_uri"] == [q["redirect_uri"]]
    assert form["client_id"] == ["moneymatch"]
    digest = hashlib.sha256(form["code_verifier"][0].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == q["code_challenge"]
    assert account.calls.last.request.headers["authorization"] == "Bearer lio_tok"
    assert revoke.called
    assert revoke.calls.last.request.headers["authorization"] == "Bearer lio_tok"

    link = await session.scalar(select(LinkedAccount))
    assert link is not None
    assert link.link_method == "oauth"
    assert link.host_account_id == "magnus"
    assert await session.get(LichessOAuthState, q["state"]) is None


@respx.mock
async def test_state_is_single_use(client):
    q = await _start(client, "o-once")
    _mock_lichess()
    body = {"code": "c", "state": q["state"]}
    ok = await client.post(CALLBACK, json=body, headers=auth_headers("o-once"))
    assert ok.status_code == 200
    again = await client.post(CALLBACK, json=body, headers=auth_headers("o-once"))
    assert again.status_code == 400
    assert again.json()["code"] == "oauth_state_invalid"


@respx.mock
async def test_state_is_bound_to_the_starting_user(client, session):
    q = await _start(client, "o-victim")
    token, _, _ = _mock_lichess()
    r = await client.post(
        CALLBACK,
        json={"code": "c", "state": q["state"]},
        headers=auth_headers("o-attacker"),
    )
    assert r.status_code == 400 and r.json()["code"] == "oauth_state_invalid"
    assert not token.called
    assert await session.get(LichessOAuthState, q["state"]) is not None


@respx.mock
async def test_unknown_state_is_rejected(client):
    await _start(client, "o-unknown")
    token, _, _ = _mock_lichess()
    r = await client.post(
        CALLBACK,
        json={"code": "c", "state": "made-up"},
        headers=auth_headers("o-unknown"),
    )
    assert r.status_code == 400 and r.json()["code"] == "oauth_state_invalid"
    assert not token.called


@respx.mock
async def test_expired_state_is_rejected(client, session):
    q = await _start(client, "o-expired")
    await session.execute(
        text("UPDATE lichess_oauth_states SET expires_at = now() - interval '1 second'")
    )
    await session.commit()
    token, _, _ = _mock_lichess()
    r = await client.post(
        CALLBACK,
        json={"code": "c", "state": q["state"]},
        headers=auth_headers("o-expired"),
    )
    assert r.status_code == 400 and r.json()["code"] == "oauth_state_invalid"
    assert not token.called


async def test_start_purges_expired_states(client, session):
    q = await _start(client, "o-purge")
    await session.execute(
        text("UPDATE lichess_oauth_states SET expires_at = now() - interval '1 second'")
    )
    await session.commit()
    await _start(client, "o-purge-2")
    session.expire_all()
    rows = await session.scalars(select(LichessOAuthState.state))
    assert q["state"] not in list(rows)


@respx.mock
async def test_rejected_code_is_oauth_denied_and_state_consumed(client, session):
    q = await _start(client, "o-denied")
    _, account, _ = _mock_lichess(token_status=400)
    r = await client.post(
        CALLBACK,
        json={"code": "bad", "state": q["state"]},
        headers=auth_headers("o-denied"),
    )
    assert r.status_code == 400 and r.json()["code"] == "oauth_denied"
    assert not account.called
    assert await session.get(LichessOAuthState, q["state"]) is None


@respx.mock
async def test_lichess_down_is_host_unavailable(client):
    q = await _start(client, "o-down")
    respx.post(TOKEN).mock(return_value=httpx.Response(503))
    r = await client.post(
        CALLBACK,
        json={"code": "c", "state": q["state"]},
        headers=auth_headers("o-down"),
    )
    assert r.status_code == 502 and r.json()["code"] == "host_unavailable"


@respx.mock
async def test_account_owned_by_another_user_conflicts(client):
    first = await _start(client, "o-first")
    _mock_lichess("Magnus")
    ok = await client.post(
        CALLBACK,
        json={"code": "c", "state": first["state"]},
        headers=auth_headers("o-first"),
    )
    assert ok.status_code == 200
    second = await _start(client, "o-second")
    _, _, revoke = _mock_lichess("Magnus")
    clash = await client.post(
        CALLBACK,
        json={"code": "c", "state": second["state"]},
        headers=auth_headers("o-second"),
    )
    assert clash.status_code == 409
    assert clash.json()["code"] == "account_already_bound"
    assert revoke.called


@respx.mock
async def test_revoke_failure_does_not_block_link(client):
    q = await _start(client, "o-revoke")
    _mock_lichess()
    respx.delete(TOKEN).mock(return_value=httpx.Response(500))
    r = await client.post(
        CALLBACK,
        json={"code": "c", "state": q["state"]},
        headers=auth_headers("o-revoke"),
    )
    assert r.status_code == 200, r.text


async def test_username_linking_is_closed_without_e2e_auth(client):
    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("o-typed"),
    )
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_username_linking_stays_closed_in_prod(client, app, monkeypatch):
    settings = app.state.settings.model_copy(
        update={"e2e_auth_enabled": True, "env": "prod"}
    )
    monkeypatch.setattr(app.state, "settings", settings)
    r = await client.post(
        "/api/v1/links",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("o-typed-prod"),
    )
    assert r.status_code == 404
