"""Typed upstream (host-API) errors.

Adapters and their host clients raise these — never raw `httpx` exceptions — so
the linking router can translate a host failure into a clean API response
(05-phase-2 · adapter resilience): `HostNotFound` → 404, `HostUnavailable` → 502.
They are deliberately *not* `APIError`s: the service layer stays transport-shaped
and the router owns the HTTP mapping.
"""

from __future__ import annotations


class HostError(Exception):
    """Base for a failed call to a host game API."""

    def __init__(self, host: str, message: str) -> None:
        super().__init__(f"[{host}] {message}")
        self.host = host
        self.message = message


class HostUnavailable(HostError):
    """The host API errored (5xx), timed out, or was unreachable after retries."""


class HostNotFound(HostError):
    """The requested resource (player/game) does not exist on the host (404)."""
