"""Typed upstream (host-API) errors."""

from __future__ import annotations


class HostError(Exception):
    """Base for a failed call to a host game API."""

    def __init__(self, host: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"[{host}] {message}")
        self.host = host
        self.message = message
        self.status_code = status_code


class HostUnavailable(HostError):
    """The host API errored (5xx), timed out, or was unreachable after retries."""


class HostNotFound(HostError):
    """The requested resource (player/game) does not exist on the host (404)."""


class HostRateLimited(HostUnavailable):
    """The host rejected the call with 429 (rate limit)."""


class HostNotConfigured(HostError):
    """The host integration has no API key configured — a deploy/config gap, not a
    transient outage or a missing player.
    """
