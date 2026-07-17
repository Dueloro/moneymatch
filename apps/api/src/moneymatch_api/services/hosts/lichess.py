"""Async client over the Lichess public API (no key required).

Ported from `poc-reference/api/_lib/lichess_service.py` (11-migration-map §1):
same endpoints and parsing, now going through the shared `request_json` helper
so every call gets retries, typed host errors, and latency logging.

The two calls that matter for linking + profiles:
  * ``GET /api/user/{username}`` — public profile + per-format perfs + counts.
  * ``GET /api/games/user/{username}`` (ndjson) — the user's games since a
    timestamp, for the metric-model bootstrap (and Phase-3 settlement).
"""

from __future__ import annotations

import json

from ._client import request_json
from .errors import HostError, HostNotFound

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
    """Fetch a public Lichess profile. ``None`` if not found/disabled/closed.

    Raises `HostUnavailable` on a host outage — a "not found" (404, or a
    disabled/closed account) is a real answer, not a failure, so it returns
    ``None`` and the adapter turns that into a clean 404.
    """
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
) -> list[dict]:
    """Fetch a user's rated games since ``since_ms`` (epoch ms), newest first.

    ``moves=true`` so plies are countable. Fails soft (``[]``) on any host error
    so a metric bootstrap / settlement poll degrades rather than crashes.
    """
    params = {
        "since": str(int(since_ms)),
        "max": str(max_games),
        "rated": "true",
        "moves": "true",
        "pgnInJson": "false",
        "clocks": "false",
        "evals": "false",
        "opening": "false",
    }
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
    specific players into one game. ``None`` on error.

    When ``users`` is given (the two linked handles), the challenge is restricted
    so only those two accounts can take the seats (`users=a,b` — 01-architecture
    §3.1). Used by Phase-3 chess brokering; kept here so the seam ports with the
    client.
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


async def get_game(game_id: str) -> dict | None:
    """Fetch a single game by id (Phase-3 grading of a brokered head-to-head)."""
    params = {
        "moves": "false",
        "clocks": "false",
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
