"""Client for the Game Coordinator sidecar.

A share code contains three ids and nothing else: no scoreboard, no demo URL.
Both come from Valve's Game Coordinator, which speaks protobuf over the Steam
network rather than HTTP, and has no maintained Python client. The bridge is a
small Node service (`gc-sidecar/`), and this is the thin wrapper over it.

Two properties of the GC that shape this client:

- **It is stateful and rate limited.** The sidecar serialises requests with
  spacing; this side adds a short timeout and a circuit breaker so a wedged GC
  degrades to a clear error instead of hanging every request behind it.
- **A missing demo URL is normal.** Valve keeps demos about a month. `expired`
  is expected on older matches and must not block settlement: the scoreboard is
  what a wager grades on, and it is still there.

The sidecar can read match data for arbitrary users, so it binds to loopback
and requires a shared secret. It must never face the internet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from ..config import get_settings

log = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 20.0

#: After this many consecutive failures, stop calling for a cooling period.
#: The GC either works or is down for a while; hammering it while it is
#: reconnecting is how you get rate limited on top of being broken.
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_SECONDS = 30.0

_failures = 0
_opened_at = 0.0


class GcError(Exception):
    """The sidecar could not answer. Carries a user-facing message."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class GcHealth:
    ready: bool
    queue_depth: int
    detail: dict[str, Any]


def _base_url() -> str:
    return get_settings().gc_sidecar_url.rstrip("/")


def _headers() -> dict[str, str]:
    secret = get_settings().gc_shared_secret
    headers = {"Accept": "application/json"}
    if secret:
        headers["X-GC-Secret"] = secret
    return headers


def _breaker_is_open() -> bool:
    if _failures < _BREAKER_THRESHOLD:
        return False
    if (time.monotonic() - _opened_at) > _BREAKER_COOLDOWN_SECONDS:
        return False
    return True


def _record_failure() -> None:
    global _failures, _opened_at
    _failures += 1
    if _failures == _BREAKER_THRESHOLD:
        _opened_at = time.monotonic()
        log.warning("gc.circuit_opened", failures=_failures)


def _record_success() -> None:
    global _failures
    if _failures:
        log.info("gc.recovered", after_failures=_failures)
    _failures = 0


def reset_breaker() -> None:
    """Test hook, and a manual recovery lever."""
    global _failures, _opened_at
    _failures = 0
    _opened_at = 0.0


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if _breaker_is_open():
        raise GcError(
            "The CS2 match service is temporarily unavailable. Try again in a moment."
        )
    url = f"{_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=_headers())
    except httpx.HTTPError as exc:
        _record_failure()
        log.warning("gc.transport_error", path=path, error=str(exc))
        raise GcError(
            "Could not reach the CS2 match service. Try again in a moment."
        ) from exc

    if response.status_code == 503:
        # The sidecar is up but not yet connected to the GC. Retryable, and
        # common right after a restart.
        _record_failure()
        raise GcError(
            "The CS2 match service is still connecting to Steam. Try again in "
            "a few seconds."
        )
    if response.status_code == 404:
        # A well-formed code Valve does not know, or one whose token has been
        # invalidated. Retrying will not help.
        _record_success()
        raise GcError(
            "Steam does not recognise that share code. Check you copied the "
            "whole code from Watch -> Your Matches.",
            retryable=False,
        )
    if response.status_code >= 400:
        _record_failure()
        log.warning("gc.error_status", path=path, status=response.status_code)
        raise GcError("The CS2 match service could not read that match.")

    _record_success()
    try:
        return response.json()
    except ValueError as exc:
        raise GcError("The CS2 match service returned an unreadable response.") from exc


async def resolve(share_code: str) -> dict[str, Any]:
    """Resolve a share code to its scoreboard.

    Returns the sidecar's payload: `matchId`, `matchTime`, `scores`, `players`,
    and `demoUrl` when the demo has not expired.
    """
    return await _post("/resolve", {"shareCode": share_code})


async def recent(steam_id: str) -> list[dict[str, Any]]:
    """The last few matches for a player, if Valve answers.

    **Opportunistic only.** Valve has restricted this over time and it may
    simply not work; a failure here is normal and must never be on a critical
    path. Returns an empty list rather than raising.
    """
    try:
        payload = await _post("/recent", {"steamId": str(steam_id)})
    except GcError as exc:
        log.info("gc.recent_unavailable", error=str(exc))
        return []
    matches = payload.get("matches")
    return matches if isinstance(matches, list) else []


async def health() -> GcHealth:
    """Whether the sidecar is up and connected. Never raises."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{_base_url()}/health", headers=_headers())
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.info("gc.health_unavailable", error=str(exc))
        return GcHealth(ready=False, queue_depth=0, detail={"error": str(exc)})
    return GcHealth(
        ready=bool(data.get("ready")),
        queue_depth=int(data.get("queueDepth") or 0),
        detail=data,
    )


__all__ = ["GcError", "GcHealth", "health", "recent", "reset_breaker", "resolve"]
