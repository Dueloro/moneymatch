"""Async client over the FaceIt Data API (v4).

Ported from `poc-reference/api/_lib/faceit_service.py` (11-migration-map §1):
same endpoints and parsing, now through the shared `request_json` helper
(retries / typed errors / latency logs). Two changes the phase doc requires:

- the API key comes from `Settings.faceit_api_key` (config.py), never
  `os.environ` at call sites;
- the finished-match stats cache is a small **TTL** cache keyed by match id
  (finished-match stats never change), sized for one process. The api and the
  worker each keep their own — no shared state.

Requires `FACEIT_API_KEY`; without it, lookups fail soft (``None``/empty) so a
missing key degrades to "can't link right now" rather than a crash.
"""

from __future__ import annotations

import time

from ...config import get_settings
from ._client import request_json
from .errors import HostError, HostNotFound

HOST = "faceit"
FACEIT_BASE = "https://open.faceit.com/data/v4"

# Finished-match stats are immutable, so a short TTL is really just a memory
# bound; keep it long enough to cover a settlement poll / bootstrap fan-out.
_MATCH_STATS_TTL_SECONDS = 3600.0
_match_stats_cache: dict[str, tuple[float, dict]] = {}


def _api_key() -> str | None:
    return get_settings().faceit_api_key


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Accept": "application/json",
        "User-Agent": "money-match/1.0",
    }


async def get_player(nickname: str, game: str = "cs2") -> dict | None:
    """Look up a FaceIt player by nickname. ``None`` if not found / no key.

    ``game`` filters to players with that game block; falls back to a gameless
    lookup so a player who lacks the block is still resolvable (the adapter then
    rejects a CS:GO-only account with a clear message).
    """
    if not _api_key():
        return None
    params = {"nickname": nickname}
    if game:
        params["game"] = game
    try:
        response = await request_json(
            HOST, "GET", f"{FACEIT_BASE}/players", headers=_headers(), params=params
        )
    except HostNotFound:
        # Retry without the game filter — the player may exist without the block.
        try:
            response = await request_json(
                HOST,
                "GET",
                f"{FACEIT_BASE}/players",
                headers=_headers(),
                params={"nickname": nickname},
            )
        except HostError:
            return None
    try:
        return response.json()
    except ValueError:
        return None


async def get_player_stats(player_id: str, game: str = "cs2") -> dict | None:
    """Lifetime stats block for a player + game. ``None`` on error / no stats."""
    if not _api_key():
        return None
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{FACEIT_BASE}/players/{player_id}/stats/{game}",
            headers=_headers(),
        )
    except HostError:
        return None
    try:
        return (response.json() or {}).get("lifetime")
    except ValueError:
        return None


async def get_player_history(
    player_id: str, game: str = "cs2", from_sec: int | None = None, limit: int = 20
) -> list[dict]:
    """A player's recent finished matches, newest first. Empty on error.

    ``from_sec`` is an epoch-seconds lower bound (FaceIt uses seconds).
    """
    if not _api_key():
        return []
    params: dict = {"game": game, "limit": str(limit)}
    if from_sec is not None:
        params["from"] = str(int(from_sec))
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{FACEIT_BASE}/players/{player_id}/history",
            headers=_headers(),
            params=params,
            timeout_s=10.0,
        )
    except HostError:
        return []
    try:
        return (response.json() or {}).get("items", [])
    except ValueError:
        return []


async def get_match_stats(match_id: str) -> dict | None:
    """Per-player stats for a finished match (``/matches/{id}/stats``).

    Returns the raw FaceIt response (``rounds`` → ``teams`` → ``players`` with a
    ``player_stats`` block), or ``None`` on error. TTL-cached in-process.
    """
    if not match_id:
        return None
    cached = _match_stats_cache.get(match_id)
    if cached is not None and (time.monotonic() - cached[0]) < _MATCH_STATS_TTL_SECONDS:
        return cached[1]
    if not _api_key():
        return None
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{FACEIT_BASE}/matches/{match_id}/stats",
            headers=_headers(),
            timeout_s=10.0,
        )
        data = response.json()
    except (HostError, ValueError):
        return None
    _match_stats_cache[match_id] = (time.monotonic(), data)
    return data


def clear_match_cache() -> None:
    """Flush the in-process match-stats cache (used in tests)."""
    _match_stats_cache.clear()
