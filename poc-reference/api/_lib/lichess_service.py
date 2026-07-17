"""Thin async client over the Lichess public API (no key required).

Phase 1 is built around the *user's own* play, so the two calls that matter are:

  * ``GET /api/user/{username}`` — public profile + per-format perfs and overall
    win/loss/draw counts. Powers the verified :class:`SkillProfile`.
  * ``GET /api/games/user/{username}`` (Accept: application/x-ndjson) — the
    user's games, filterable by ``since`` timestamp, ``rated``, and ``perfType``.
    Powers settlement: we discover qualifying games played after a contract was
    activated and grade against their real outcomes.

These map to the ``fetch_profile`` and ``poll_eligible_games`` methods of the
chess GameAdapter.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

LICHESS_BASE = "https://lichess.org/api"
HEADERS = {"User-Agent": "money-match/1.0 (skill-contract demo)"}


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


async def get_user(username: str) -> Optional[dict]:
    """Fetch a public Lichess profile. Returns ``None`` if not found/disabled."""
    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.get(f"{LICHESS_BASE}/user/{username}", timeout=8)
            r.raise_for_status()
        except httpx.HTTPError:
            return None
    data = r.json()
    if data.get("disabled") or data.get("closed"):
        return None
    return data


async def get_user_games(
    username: str,
    since_ms: int,
    perf_types: Optional[set[str]] = None,
    max_games: int = 50,
) -> list[dict]:
    """Fetch a user's games since ``since_ms`` (epoch ms), newest first.

    ``moves=true`` so we can count plies for move-based objectives. Filters to
    rated games; ``perf_types`` (e.g. {"blitz"}) narrows by time control.
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

    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.get(
                f"{LICHESS_BASE}/games/user/{username}",
                headers={**HEADERS, "Accept": "application/x-ndjson"},
                params=params,
                timeout=12,
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return []
    return _parse_ndjson(r.text)


async def create_open_challenge(clock_limit: int, clock_increment: int = 0) -> Optional[dict]:
    """Create a Lichess **open challenge** (no auth): anyone with a color URL can
    join, so the platform can pair two specific players into one game.

    Returns ``{"game_id", "urls": {"white", "black"}}`` or ``None`` on error.
    """
    data = {"clock.limit": str(clock_limit), "clock.increment": str(clock_increment), "name": "Money Match"}
    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.post(f"{LICHESS_BASE}/challenge/open", data=data, timeout=8)
            r.raise_for_status()
            j = r.json()
        except (httpx.HTTPError, ValueError):
            return None
    game_id = j.get("id")
    if not game_id:
        return None
    return {"game_id": game_id, "urls": {"white": j.get("urlWhite"), "black": j.get("urlBlack")}}


async def get_game(game_id: str) -> Optional[dict]:
    """Fetch a single game by id (for grading a brokered head-to-head)."""
    params = {"moves": "false", "clocks": "false", "evals": "false", "opening": "false"}
    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.get(
                f"https://lichess.org/game/export/{game_id}",
                headers={**HEADERS, "Accept": "application/json"},
                params=params,
                timeout=8,
            )
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return None


async def get_current_game(username: str) -> Optional[dict]:
    """Fetch a user's current (ongoing, else most recent) game as JSON.

    Uses the public ``/api/user/{username}/current-game`` endpoint with moves +
    clocks so the spectator view can render a move list and the clocks. Returns
    ``None`` when the user has no game to show (404) or on any error.
    """
    params = {
        "moves": "true",
        "clocks": "true",
        "tags": "true",
        "pgnInJson": "false",
        "opening": "false",
        "evals": "false",
    }
    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.get(
                f"{LICHESS_BASE}/user/{username}/current-game",
                headers={**HEADERS, "Accept": "application/json"},
                params=params,
                timeout=8,
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return None
    try:
        return r.json()
    except ValueError:
        return None
