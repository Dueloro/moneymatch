"""Async client over the Lichess public API (no key required)."""

from __future__ import annotations

import json

import httpx

from ._client import request_json
from .errors import HostError, HostNotFound, HostUnavailable

HOST = "lichess"
LICHESS_BASE = "https://lichess.org/api"
HEADERS = {"User-Agent": "money-match/1.0 (skill-contract platform)"}


def _parse_ndjson(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


async def get_user(username: str) -> dict | None:
    """Fetch a public Lichess profile."""
    try:
        response = await request_json(
            HOST, "GET", f"{LICHESS_BASE}/user/{username}", headers=HEADERS
        )
    except HostNotFound:
        return None
    data = response.json()
    if data.get("disabled") or data.get("closed"):
        return None
    return data


async def get_user_games(
    username: str,
    since_ms: int,
    perf_types: set[str] | None = None,
    max_games: int = 50,
    rated_only: bool = True,
) -> list[dict]:
    """Fetch a user's games since ``since_ms`` (epoch ms), newest first."""
    params = {
        "since": str(int(since_ms)),
        "max": str(max_games),
        "moves": "true",
        "pgnInJson": "false",
        "clocks": "false",
        "evals": "false",
        "opening": "false",
    }
    if rated_only:
        params["rated"] = "true"
    if perf_types:
        params["perfType"] = ",".join(sorted(perf_types))
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{LICHESS_BASE}/games/user/{username}",
            headers={**HEADERS, "Accept": "application/x-ndjson"},
            params=params,
            timeout_s=12.0,
        )
    except HostError:
        return []
    return _parse_ndjson(response.text)


async def create_open_challenge(
    clock_limit: int, clock_increment: int = 0, *, users: list[str] | None = None
) -> dict | None:
    """Create a Lichess **open challenge** (no auth) so the platform can pair two
    specific players into one game.
    """
    data = {
        "clock.limit": str(clock_limit),
        "clock.increment": str(clock_increment),
        "name": "Money Match",
    }
    if users:
        data["users"] = ",".join(users)
    try:
        response = await request_json(
            HOST,
            "POST",
            f"{LICHESS_BASE}/challenge/open",
            headers=HEADERS,
            data=data,
        )
        j = response.json()
    except (HostError, ValueError):
        return None
    game_id = j.get("id")
    if not game_id:
        return None
    return {
        "game_id": game_id,
        "urls": {"white": j.get("urlWhite"), "black": j.get("urlBlack")},
    }


async def get_live_game(game_id: str) -> dict | None:
    """One game with its SAN moves and clocks (centiseconds per ply). Grading and the
    live board share this call. Lichess delays ongoing games by 3 moves.
    """
    params = {
        "moves": "true",
        "clocks": "true",
        "evals": "false",
        "opening": "false",
    }
    try:
        response = await request_json(
            HOST,
            "GET",
            f"https://lichess.org/game/export/{game_id}",
            headers={**HEADERS, "Accept": "application/json"},
            params=params,
        )
        return response.json()
    except (HostError, ValueError):
        return None


LICHESS_OAUTH_AUTHORIZE = "https://lichess.org/oauth"


def _json_object(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise HostUnavailable(HOST, "malformed JSON") from exc
    if not isinstance(data, dict):
        raise HostUnavailable(HOST, "unexpected JSON shape")
    return data


async def exchange_oauth_code(
    code: str, code_verifier: str, redirect_uri: str, client_id: str
) -> str:
    """Trade an authorization code (PKCE) for an access token."""
    response = await request_json(
        HOST,
        "POST",
        f"{LICHESS_BASE}/token",
        headers=HEADERS,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
        },
        retry=False,
    )
    token = _json_object(response).get("access_token")
    if not isinstance(token, str) or not token:
        raise HostError(HOST, "token response had no access_token")
    return token


async def get_account(token: str) -> dict:
    """The account the token belongs to."""
    response = await request_json(
        HOST,
        "GET",
        f"{LICHESS_BASE}/account",
        headers={**HEADERS, "Authorization": f"Bearer {token}"},
    )
    return _json_object(response)


async def revoke_token(token: str) -> None:
    await request_json(
        HOST,
        "DELETE",
        f"{LICHESS_BASE}/token",
        headers={**HEADERS, "Authorization": f"Bearer {token}"},
    )
