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

    def __init__(self, host: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"[{host}] {message}")
        self.host = host
        self.message = message
        #: The upstream HTTP status, where there was one.
        #:
        #: Most callers only need "did this fail". Valve's share-code chain
        #: needs more: 412 means the cursor is not this player's and must never
        #: be retried, 403 means their auth code is dead and they have to be
        #: told, 429 means back off. Those are three different actions, and
        #: recovering them by parsing an error string would be a decision about
        #: money made by substring match.
        self.status_code = status_code


class HostUnavailable(HostError):
    """The host API errored (5xx), timed out, or was unreachable after retries."""


class HostNotFound(HostError):
    """The requested resource (player/game) does not exist on the host (404)."""


class HostNotConfigured(HostError):
    """The host integration has no API key configured — a deploy/config gap, not
    a transient outage or a missing player. Raised (never swallowed to ``None``)
    so linking surfaces an actionable message and ops can see the misconfig,
    instead of every lookup masquerading as "player not found"."""
