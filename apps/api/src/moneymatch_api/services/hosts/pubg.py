"""Async client over the official PUBG (gamelocker) API — direct, not via FaceIt.

Same shape as the other host clients (05-phase-2): keyed requests through the
shared `request_json` helper (retries / typed errors / latency logs), with the
key sourced from `Settings.pubg_api_key` (never `os.environ` at call sites).

PUBG specifics:
- Base is `https://api.pubg.com/shards/{shard}` — the shard is the platform
  (`steam` for PC; `psn` / `xbox` for console). It's the suffix of the game id
  (`pubg.steam` → `steam`).
- Requests must send `Accept: application/vnd.api+json` (JSON:API).
- The public rate limit is ~10 req/min, so callers cap match fan-out and rely on
  the finished-match TTL cache below.

Requires `PUBG_API_KEY`; without it every lookup fails soft (``None`` / empty),
so a missing key degrades to "can't link right now" rather than a crash.
"""

from __future__ import annotations

import time

from ...config import get_settings
from ._client import request_json
from .errors import HostError, HostNotConfigured, HostNotFound, HostUnavailable

HOST = "pubg"
PUBG_BASE = "https://api.pubg.com/shards"

# Finished matches are immutable — the TTL is just a memory bound, kept long
# enough to cover a settlement poll / metric-model bootstrap fan-out.
_MATCH_TTL_SECONDS = 3600.0
_match_cache: dict[str, tuple[float, dict]] = {}


def _api_key() -> str | None:
    return get_settings().pubg_api_key


def is_configured() -> bool:
    """True when a PUBG API key is set. The link path checks this up front so a
    missing key is a clear `HostNotConfigured`, not a silent "player not found"."""
    return bool(_api_key())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Accept": "application/vnd.api+json",
        "User-Agent": "money-match/1.0",
    }


async def get_player_by_name(name: str, shard: str = "steam") -> dict | None:
    """Resolve a PUBG player by display name. Returns the JSON:API player
    resource (``id`` = ``account.…``, ``attributes.name``, recent match ids under
    ``relationships.matches.data``), or ``None`` when no such player exists.

    This is the link-verification path, so it does *not* swallow every failure
    into ``None``: a missing key raises `HostNotConfigured`, and an outage / auth
    / rate-limit error (`HostUnavailable` / `HostError`) propagates. Only a
    genuine "no such player" (404 or an empty result set) returns ``None`` — so
    the adapter's "player not found" means exactly that."""
    if not _api_key():
        raise HostNotConfigured(HOST, "PUBG_API_KEY is not configured")
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{PUBG_BASE}/{shard}/players",
            headers=_headers(),
            params={"filter[playerNames]": name},
        )
    except HostNotFound:
        return None
    try:
        data = (response.json() or {}).get("data") or []
    except ValueError:
        return None
    return data[0] if data else None


async def get_player_by_id(account_id: str, shard: str = "steam") -> dict | None:
    """Re-fetch a player resource by its stable ``account.…`` id."""
    if not _api_key():
        return None
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{PUBG_BASE}/{shard}/players/{account_id}",
            headers=_headers(),
        )
    except HostUnavailable:
        # Outage / rate-limit (429): propagate so settlement grading extends the
        # window instead of reading it as "no such player / no qualifying game".
        raise
    except HostError:
        return None  # 404 / other 4xx → "no such player / unreadable"
    try:
        return (response.json() or {}).get("data")
    except ValueError:
        return None


async def get_lifetime(account_id: str, shard: str = "steam") -> dict | None:
    """Lifetime per-game-mode stats for a player (``…/seasons/lifetime``).

    Returns the ``gameModeStats`` map (mode → totals), or ``None`` on error.
    """
    if not _api_key():
        return None
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{PUBG_BASE}/{shard}/players/{account_id}/seasons/lifetime",
            headers=_headers(),
            timeout_s=10.0,
        )
    except HostError:
        # Deliberately fail-soft on ALL host errors (incl. outages): lifetime is a
        # soft profile / bracketing signal, never settlement. A momentary gap must
        # not fail linking; the profile just computes from what modes returned.
        return None
    try:
        attrs = ((response.json() or {}).get("data") or {}).get("attributes") or {}
    except ValueError:
        return None
    return attrs.get("gameModeStats")


async def get_match(match_id: str, shard: str = "steam") -> dict | None:
    """A finished match (``…/matches/{id}``), returning the raw JSON:API document
    (``data.attributes`` + ``included`` participants). TTL-cached in-process."""
    if not match_id:
        return None
    cached = _match_cache.get(match_id)
    if cached is not None and (time.monotonic() - cached[0]) < _MATCH_TTL_SECONDS:
        return cached[1]
    if not _api_key():
        return None
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{PUBG_BASE}/{shard}/matches/{match_id}",
            headers=_headers(),
            timeout_s=10.0,
        )
        data = response.json()
    except HostUnavailable:
        # An unreadable match might be the qualifying one — propagate so grading
        # extends the window rather than silently grading a later match.
        raise
    except (HostError, ValueError):
        return None  # 404 (expired match) / other 4xx / bad JSON → skip this match
    _match_cache[match_id] = (time.monotonic(), data)
    return data


def clear_match_cache() -> None:
    """Flush the in-process match cache (used in tests)."""
    _match_cache.clear()
