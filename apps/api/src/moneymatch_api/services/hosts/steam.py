"""Async client over the Steam Web API.

Three things we ask Steam for, and one we deliberately do not.

- **Ban status** (`GetPlayerBans`) at link time. Cheap, and you want it before
  money moves.
- **A skill prior** (`GetUserStatsForGame`, appid 730). `total_kills /
  total_deaths` is a usable lifetime K/D. Two caveats that are encoded here
  rather than glossed: it is cumulative across casual, deathmatch and bot
  games, so it is a weak prior; and it needs the profile's *Game details* to be
  public, which most are not. A private profile is normal, not an error.
- **Profile summary** (`GetPlayerSummaries`) for the display name and avatar.

What we never do: accept a Steam **display name** as identity. Persona names
are not unique, not searchable through any API, and freely mutable. On a wager
product, taking one as identity is a straightforward impersonation vector.
`ResolveVanityURL` resolves a *custom profile URL* only, and is offered purely
as a convenience for pasted profile links.

Requires `STEAM_API_KEY`. Without it every call fails soft (``None``), so a
missing key degrades to "no ban info, default prior" rather than a crash.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from ...config import get_settings
from ._client import request_json
from .errors import HostError, HostNotConfigured

HOST = "steam"
STEAM_BASE = "https://api.steampowered.com"
CS2_APPID = "730"

log = structlog.get_logger(__name__)


def _api_key() -> str | None:
    key = get_settings().steam_api_key
    return key.strip() if key else None


def is_configured() -> bool:
    return bool(_api_key())


@dataclass(frozen=True)
class BanStatus:
    """What Steam says about a player's standing."""

    vac_banned: bool
    number_of_vac_bans: int
    game_bans: int
    days_since_last_ban: int
    community_banned: bool
    economy_ban: str

    @property
    def is_clean(self) -> bool:
        return not (self.vac_banned or self.game_bans or self.community_banned)


@dataclass(frozen=True)
class LifetimeStats:
    """CS2 lifetime counters, when the profile exposes them."""

    total_kills: int
    total_deaths: int
    total_time_played: int
    total_matches_won: int
    total_matches_played: int

    @property
    def kd_ratio(self) -> float | None:
        if self.total_deaths <= 0:
            return None
        return self.total_kills / self.total_deaths


async def _get(path: str, params: dict[str, str]) -> dict | None:
    key = _api_key()
    if not key:
        return None
    try:
        response = await request_json(
            HOST, "GET", f"{STEAM_BASE}{path}", params={**params, "key": key}
        )
    except HostError as exc:
        log.warning("steam.request_failed", path=path, error=str(exc))
        return None
    try:
        return response.json()
    except ValueError:
        log.warning("steam.bad_json", path=path)
        return None


async def get_player_summary(steam_id: str) -> dict | None:
    """Persona name, avatar and profile visibility. ``None`` if unknown."""
    data = await _get("/ISteamUser/GetPlayerSummaries/v2/", {"steamids": str(steam_id)})
    players = ((data or {}).get("response") or {}).get("players") or []
    return players[0] if players else None


async def get_player_bans(steam_id: str) -> BanStatus | None:
    """VAC / game / community ban status. ``None`` when unavailable."""
    data = await _get("/ISteamUser/GetPlayerBans/v1/", {"steamids": str(steam_id)})
    players = (data or {}).get("players") or []
    if not players:
        return None
    row = players[0]
    return BanStatus(
        vac_banned=bool(row.get("VACBanned")),
        number_of_vac_bans=int(row.get("NumberOfVACBans") or 0),
        game_bans=int(row.get("NumberOfGameBans") or 0),
        days_since_last_ban=int(row.get("DaysSinceLastBan") or 0),
        community_banned=bool(row.get("CommunityBanned")),
        economy_ban=str(row.get("EconomyBan") or "none"),
    )


async def get_cs2_lifetime_stats(steam_id: str) -> LifetimeStats | None:
    """CS2 lifetime counters, or ``None`` when the profile keeps them private.

    Steam answers a private profile with a 403, which `_get` turns into
    ``None``. That is the common case, not a failure: most profiles do not
    expose game details, and the caller falls back to a default prior.
    """
    data = await _get(
        "/ISteamUserStats/GetUserStatsForGame/v2/",
        {"appid": CS2_APPID, "steamid": str(steam_id)},
    )
    stats = ((data or {}).get("playerstats") or {}).get("stats") or []
    if not stats:
        return None
    by_name = {s.get("name"): int(s.get("value") or 0) for s in stats}
    if "total_kills" not in by_name:
        return None
    return LifetimeStats(
        total_kills=by_name.get("total_kills", 0),
        total_deaths=by_name.get("total_deaths", 0),
        total_time_played=by_name.get("total_time_played", 0),
        total_matches_won=by_name.get("total_matches_won", 0),
        total_matches_played=by_name.get("total_matches_played", 0),
    )


async def resolve_vanity_url(vanity: str) -> str | None:
    """A custom profile URL to a SteamID64. Never a display name.

    Steam's own endpoint only accepts the custom URL segment, which is unique
    and owned. It cannot be given a persona name, and this wrapper must never
    be extended to search by one.
    """
    data = await _get("/ISteamUser/ResolveVanityURL/v1/", {"vanityurl": vanity.strip()})
    response = (data or {}).get("response") or {}
    if response.get("success") != 1:
        return None
    return str(response.get("steamid")) or None


class ChainError(Exception):
    """A share-code chain poll that failed in a way the caller must act on.

    `retryable` separates "try again later" from "this will never work until
    the player does something". Retrying a 412 forever would hammer Valve with
    a request that cannot succeed, and repeated bad auth codes get the whole
    API key temporarily blocked -- one user's stale cursor would then take
    settlement down for everyone.
    """

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


#: Returned by `get_next_share_code` when the player has no newer match.
CAUGHT_UP = "caught_up"


async def get_next_share_code(
    steam_id: str, auth_code: str, known_code: str
) -> str | None:
    """The share code for the match *after* `known_code`, or None if caught up.

    This is what removes the paste step. Valve stores a player's matches as a
    linked list: given one code you own, it hands back the next, so a one-time
    cursor turns into every future match arriving on its own.

    The status codes carry the entire contract, and they are not interchangeable:

    - **202** — no newer match yet. Normal, and the common case; a player who
      has not played since the last poll is not an error.
    - **412** — `known_code` is not this player's match. Their cursor is wrong
      and no amount of retrying will fix it, so this stops and re-prompts.
    - **403** — the auth code is bad or was regenerated. The link is broken
      until they supply a new one.
    - **429/5xx** — rate limited or down. Back off and try later.
    """
    key = _api_key()
    if not key:
        raise HostNotConfigured(HOST, "STEAM_API_KEY is not configured.")

    try:
        response = await request_json(
            HOST,
            "GET",
            f"{STEAM_BASE}/ICSGOPlayers_730/GetNextMatchSharingCode/v1/",
            # The auth code is a per-user secret. It goes in the query because
            # Valve accepts nothing else, and it is never logged: `host.request`
            # logs the URL, so anything secret must stay out of the path.
            params={
                "key": key,
                "steamid": str(steam_id),
                "steamidkey": auth_code,
                "knowncode": known_code,
            },
        )
    except HostError as exc:
        status = exc.status_code
        if status == 412:
            raise ChainError(
                "chain_cursor_not_yours",
                "That share code is not from a match on this Steam account. "
                "Paste one of your own to start the chain.",
                retryable=False,
            ) from exc
        if status == 403:
            raise ChainError(
                "chain_auth_code_rejected",
                "Steam rejected your authentication code. Create a new one and "
                "reconnect.",
                retryable=False,
            ) from exc
        raise ChainError(
            "chain_unavailable",
            "Steam would not answer just now. This will retry on its own.",
            retryable=True,
        ) from exc

    # 202 is Valve's "nothing newer", and it carries no body worth reading.
    if response.status_code == 202:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    code = ((payload or {}).get("result") or {}).get("nextcode")
    # Valve answers "n/a" rather than 202 in some caught-up cases.
    if not code or str(code).lower() in {"n/a", "none"}:
        return None
    return str(code)


__all__ = [
    "CAUGHT_UP",
    "ChainError",
    "get_next_share_code",
    "BanStatus",
    "LifetimeStats",
    "get_cs2_lifetime_stats",
    "get_player_bans",
    "get_player_summary",
    "is_configured",
    "resolve_vanity_url",
]
