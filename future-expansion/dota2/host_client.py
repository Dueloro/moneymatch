"""Async client over the OpenDota API (Dota 2, no key required).

Ported from `poc-reference/api/_lib/opendota_service.py` (11-migration-map §1):
same endpoints, rank helpers, and private-profile handling, now through the
shared `request_json` helper (retries / typed errors / latency logs).

Public Dota 2 data is keyed on a numeric Steam32 ``account_id``:
  * ``GET /players/{id}`` — profile (persona, avatar, rank tier, mmr estimate).
  * ``GET /players/{id}/wl`` — lifetime win/loss counts.
  * ``GET /players/{id}/recentMatches`` — recent matches with ``player_slot`` +
    ``radiant_win`` (win/loss) and per-match rate stats (KDA, GPM).
  * ``GET /search?q=`` — resolve a persona name to candidate ``account_id``s.
"""

from __future__ import annotations

from typing import Any

from ._client import request_json
from .errors import HostError

HOST = "opendota"
OPENDOTA_BASE = "https://api.opendota.com/api"
HEADERS = {"User-Agent": "money-match/1.0", "Accept": "application/json"}

# Dota 2 medal names by rank-tier tens digit (ones digit = stars).
_MEDALS = {
    1: "Herald",
    2: "Guardian",
    3: "Crusader",
    4: "Archon",
    5: "Legend",
    6: "Ancient",
    7: "Divine",
    8: "Immortal",
}


def rank_label(rank_tier: int | None) -> str | None:
    """Human medal label, e.g. 55 → 'Legend 5', 80 → 'Immortal'."""
    if not rank_tier:
        return None
    medal, stars = divmod(int(rank_tier), 10)
    name = _MEDALS.get(medal)
    if not name:
        return None
    return f"{name} {stars}" if stars and medal < 8 else name


def mmr_from_rank(rank_tier: int | None) -> int:
    """Approximate MMR from a rank tier — a numeric strength for bracketing when
    OpenDota hides the real ``mmr_estimate`` (common for ranked players)."""
    if not rank_tier:
        return 3000
    medal, stars = divmod(int(rank_tier), 10)
    return (medal - 1) * 770 + stars * 150 + 154


async def _get(path: str, params: dict | None = None) -> Any:
    """GET + JSON, failing soft to ``None`` on any host error (matches the PoC:
    the caller treats a private/unknown profile as "not found")."""
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{OPENDOTA_BASE}{path}",
            headers=HEADERS,
            params=params,
            timeout_s=10.0,
        )
        return response.json()
    except (HostError, ValueError):
        return None


async def get_player(account_id: str) -> dict | None:
    data = await _get(f"/players/{account_id}")
    # An unknown id returns 200 with {"profile": null}; treat that as not found.
    if not data or not data.get("profile"):
        return None
    return data


async def get_player_wl(account_id: str) -> dict:
    return await _get(f"/players/{account_id}/wl") or {"win": 0, "lose": 0}


async def get_recent_matches(account_id: str, limit: int = 20) -> list[dict]:
    return (
        await _get(f"/players/{account_id}/recentMatches", params={"limit": str(limit)})
        or []
    )


async def search_players(query: str, limit: int = 10) -> list[str]:
    """Candidate account_ids for a persona name, most-recently-active first.

    Returns several because many Dota profiles are private (no public stats); the
    caller tries them in order until one resolves to a public profile.
    """
    results = await _get("/search", params={"q": query.strip()}) or []
    results.sort(key=lambda r: r.get("last_match_time") or "", reverse=True)
    return [
        str(r["account_id"]) for r in results[:limit] if r.get("account_id") is not None
    ]
