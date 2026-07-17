"""Thin async client over the FaceIt Data API (v4).

FaceIt is the second supported title family (roadmap §3/§5 — multi-game). The
calls that matter for identity + stats:

  * ``GET /players?nickname={n}`` — public player by nickname, including the
    per-game block (skill level, FaceIt elo, region). Powers the verified
    :class:`SkillProfile` for a FaceIt game.
  * ``GET /players/{id}/stats/{game}`` — lifetime stats (matches, win rate,
    average K/D, …) used to enrich the profile.

Requires an API key (``FACEIT_API_KEY`` in the environment / ``.env``). All
calls fail soft (return ``None``/empty) so a missing key or outage degrades to
"can't link right now" rather than a crash.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

try:  # Load .env when present (dev). Harmless if python-dotenv is absent.
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())
except Exception:  # noqa: BLE001
    pass

FACEIT_BASE = "https://open.faceit.com/data/v4"


def _api_key() -> Optional[str]:
    return os.environ.get("FACEIT_API_KEY")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Accept": "application/json",
        "User-Agent": "money-match/1.0",
    }


async def get_player(nickname: str, game: str = "cs2") -> Optional[dict]:
    """Look up a FaceIt player by nickname. Returns ``None`` if not found.

    ``game`` filters to players who have that game block (e.g. "cs2").
    """
    if not _api_key():
        return None
    params = {"nickname": nickname}
    if game:
        params["game"] = game
    async with httpx.AsyncClient(headers=_headers()) as client:
        try:
            r = await client.get(f"{FACEIT_BASE}/players", params=params, timeout=8)
            r.raise_for_status()
        except httpx.HTTPError:
            # Fall back to a gameless lookup (the player may not have the game block).
            try:
                r = await client.get(f"{FACEIT_BASE}/players", params={"nickname": nickname}, timeout=8)
                r.raise_for_status()
            except httpx.HTTPError:
                return None
    try:
        return r.json()
    except ValueError:
        return None


async def get_player_stats(player_id: str, game: str = "cs2") -> Optional[dict]:
    """Lifetime stats block for a player + game. ``None`` on error/no stats."""
    if not _api_key():
        return None
    async with httpx.AsyncClient(headers=_headers()) as client:
        try:
            r = await client.get(f"{FACEIT_BASE}/players/{player_id}/stats/{game}", timeout=8)
            r.raise_for_status()
        except httpx.HTTPError:
            return None
    try:
        return (r.json() or {}).get("lifetime")
    except ValueError:
        return None


async def get_player_history(
    player_id: str, game: str = "cs2", from_sec: Optional[int] = None, limit: int = 20
) -> list[dict]:
    """A player's recent finished matches, newest first. Empty on error.

    ``from_sec`` is an epoch-seconds lower bound (FaceIt uses seconds). Each item
    carries ``results.winner`` and the per-faction player lists, enough to grade
    a head-to-head outcome for the linked player.
    """
    if not _api_key():
        return []
    params: dict = {"game": game, "limit": str(limit)}
    if from_sec is not None:
        params["from"] = str(int(from_sec))
    async with httpx.AsyncClient(headers=_headers()) as client:
        try:
            r = await client.get(f"{FACEIT_BASE}/players/{player_id}/history", params=params, timeout=10)
            r.raise_for_status()
        except httpx.HTTPError:
            return []
    try:
        return (r.json() or {}).get("items", [])
    except ValueError:
        return []


# Finished-match stats never change, so cache them in-process for the request
# batch (a settlement poll or a Lab load fetches the same matches repeatedly).
_match_stats_cache: dict[str, dict] = {}


async def get_match_stats(match_id: str) -> Optional[dict]:
    """Per-player stats for a finished match (``/matches/{id}/stats``).

    Returns the raw FaceIt response (``rounds`` → ``teams`` → ``players`` with a
    ``player_stats`` block), or ``None`` on error. Cached in-process. A single
    429 is retried honoring ``Retry-After`` because the Lab fans out one call per
    recent match.
    """
    if not match_id:
        return None
    if match_id in _match_stats_cache:
        return _match_stats_cache[match_id]
    if not _api_key():
        return None
    async with httpx.AsyncClient(headers=_headers()) as client:
        for attempt in range(2):
            try:
                r = await client.get(f"{FACEIT_BASE}/matches/{match_id}/stats", timeout=10)
                if r.status_code == 429 and attempt == 0:
                    await asyncio.sleep(min(5, int(r.headers.get("Retry-After", "1") or "1")))
                    continue
                r.raise_for_status()
            except httpx.HTTPError:
                return None
            break
    try:
        data = r.json()
    except ValueError:
        return None
    _match_stats_cache[match_id] = data
    return data


def clear_match_cache() -> None:
    """Flush the in-process match-stats cache (used in tests)."""
    _match_stats_cache.clear()
