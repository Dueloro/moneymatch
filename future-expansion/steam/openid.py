"""Steam OpenID 2.0 sign-in.

Steam never implemented OpenID Connect, so this is the older OpenID 2.0 dance.
It is short, and the security of the whole thing rests on one step:

    the callback's parameters are sent *back to Steam* for verification.

Anyone can craft a URL that looks like a Steam callback and names any SteamID.
The only thing that makes the claim trustworthy is Steam confirming it signed
those exact parameters, which is what `verify_callback` does. Reading the
SteamID out of `claimed_id` without that round trip would let anyone sign in as
anyone.

What comes back is a SteamID64 and nothing else. That is the point: it is an
identity Valve vouches for, unlike a persona name, which is mutable, non-unique
and unsearchable.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx
import structlog

from ..config import get_settings

log = structlog.get_logger(__name__)

STEAM_OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
_NS = "http://specs.openid.net/auth/2.0"

#: Steam returns the identity as a profile URL ending in the SteamID64.
_CLAIMED_ID_RE = re.compile(r"^https?://steamcommunity\.com/openid/id/(\d{17})$")

_VERIFY_TIMEOUT_SECONDS = 15.0


class SteamAuthError(Exception):
    """Sign-in could not be verified. Never leaks the raw parameters."""


def login_url(return_url: str | None = None, realm: str | None = None) -> str:
    """The URL to send a user to in order to sign in through Steam.

    `realm` is the site Steam shows on its consent screen and must be a prefix
    of `return_to`, or Steam refuses the request outright.
    """
    settings = get_settings()
    params = {
        "openid.ns": _NS,
        "openid.mode": "checkid_setup",
        "openid.return_to": return_url or settings.resolved_steam_openid_return_url,
        "openid.realm": realm or settings.resolved_steam_openid_realm,
        # We are not naming a user; Steam picks whoever is signed in.
        "openid.identity": _IDENTIFIER_SELECT,
        "openid.claimed_id": _IDENTIFIER_SELECT,
    }
    return f"{STEAM_OPENID_ENDPOINT}?{urlencode(params)}"


async def verify_callback(params: dict[str, str]) -> str:
    """Verify a Steam OpenID callback and return the SteamID64.

    Raises `SteamAuthError` unless Steam itself confirms it signed these
    parameters. Everything else in this function is a precondition check; the
    round trip is the actual security.
    """
    if params.get("openid.mode") != "id_res":
        raise SteamAuthError("Steam sign-in was cancelled or did not complete.")

    claimed_id = params.get("openid.claimed_id", "")
    match = _CLAIMED_ID_RE.match(claimed_id)
    if match is None:
        raise SteamAuthError("Steam returned an identity we could not read.")
    steam_id = match.group(1)

    # Hand every parameter straight back with mode swapped. Steam re-checks its
    # own signature over exactly the fields it signed, so nothing here may be
    # filtered or reordered on our side.
    verification = dict(params)
    verification["openid.mode"] = "check_authentication"

    try:
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT_SECONDS) as client:
            response = await client.post(STEAM_OPENID_ENDPOINT, data=verification)
    except httpx.HTTPError as exc:
        log.warning("steam.openid_verify_unreachable", error=str(exc))
        raise SteamAuthError(
            "Could not reach Steam to confirm your sign-in. Try again."
        ) from exc

    body = response.text or ""
    if "is_valid:true" not in body:
        # Either a forged callback or a replayed one. Both are the same answer.
        log.warning("steam.openid_verify_rejected", steam_id=steam_id)
        raise SteamAuthError("Steam did not confirm that sign-in.")

    log.info("steam.openid_verified", steam_id=steam_id)
    return steam_id


__all__ = ["STEAM_OPENID_ENDPOINT", "SteamAuthError", "login_url", "verify_callback"]
