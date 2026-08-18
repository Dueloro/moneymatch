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
from typing import Any, Literal

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


#: What the sidecar is actually doing. These are **not** interchangeable and the
#: distinction is the whole point of this type.
#:
#: `ready: false` used to mean either "the process is up but has not attached to
#: the Game Coordinator" or "there is no process at all" — the same shape for
#: both, with the `detail` that would have told them apart discarded by the
#: router. That ambiguity is why a deployed sidecar sat unattached for three
#: days without anyone being able to say which failure it was.
#:
#: - `attached`          — up and talking to the GC. Share codes resolve.
#: - `up_but_unattached` — process answers, GC session not established. Usually
#:                         a bad or missing refresh token, or a Steam hiccup.
#:                         Recovers on its own or needs a new token.
#: - `unreachable`       — nothing answered. Not deployed, wrong address,
#:                         network path broken. Needs a deploy or config fix.
#: - `circuit_open`      — we stopped calling after repeated failures. Says
#:                         nothing about the sidecar; says something about us.
GcStatus = Literal["attached", "up_but_unattached", "unreachable", "circuit_open"]


@dataclass(frozen=True)
class GcHealth:
    ready: bool
    queue_depth: int
    detail: dict[str, Any]
    status: GcStatus = "unreachable"

    @property
    def is_healthy(self) -> bool:
        return self.status == "attached"


def _base_url() -> str:
    base = get_settings().gc_sidecar_url.strip().rstrip("/")
    # Platforms hand out an internal address as bare "host:port" (Render's
    # `hostport`), which httpx rejects for having no scheme. Defaulting to http
    # is right for a private network: TLS between two containers on the same
    # private network buys nothing, and this address is not routable from
    # outside it.
    if base and "://" not in base:
        base = f"http://{base}"
    return base


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
    """What the sidecar is doing, as a discriminated status. Never raises.

    Every branch returns a **different** `status`, because "not deployed" and
    "deployed but not attached" need different people to do different things,
    and previously both surfaced as `ready: false` with the distinguishing
    detail thrown away.
    """
    if _breaker_is_open():
        # We are not calling, so we genuinely do not know what the sidecar is
        # doing. Saying "unreachable" here would blame the sidecar for our own
        # back-off.
        return GcHealth(
            ready=False,
            queue_depth=0,
            detail={"error": "circuit breaker open", "failures": _failures},
            status="circuit_open",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{_base_url()}/health", headers=_headers())
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.info("gc.health_unavailable", error=str(exc), url=_base_url())
        return GcHealth(
            ready=False,
            queue_depth=0,
            detail={"error": str(exc), "error_type": type(exc).__name__,
                    "url": _base_url()},
            status="unreachable",
        )

    ready = bool(data.get("ready"))
    if not ready:
        log.warning("gc.up_but_unattached", detail=data)
    return GcHealth(
        ready=ready,
        queue_depth=int(data.get("queueDepth") or 0),
        detail=data,
        status="attached" if ready else "up_but_unattached",
    )


__all__ = ["GcError", "GcHealth", "health", "recent", "reset_breaker", "resolve"]
