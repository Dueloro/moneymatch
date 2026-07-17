"""Server-side product analytics (PostHog) — 09-phase-6 · deliverable 3.

Client-only analytics can't see the settlement worker, so the money/liquidity
events (`entry_queued`, `match_found`, `contest_settled`, `rake_collected`,
`refund_issued`) are captured here, server-side. The event names are stable and
mirror the client telemetry seam (`apps/web/src/lib/telemetry.ts`).

Guarded like Sentry: with no `POSTHOG_API_KEY` configured the whole module is a
no-op, so tests and local runs never touch the network. Capture is best-effort —
a telemetry failure never breaks a money path (it is caught and logged).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from ..config import get_settings

log = structlog.get_logger(__name__)

# Stable server-observed event names (keep in lockstep with the client seam).
ENTRY_QUEUED = "entry_queued"
MATCH_FOUND = "match_found"
CONTEST_SETTLED = "contest_settled"
RAKE_COLLECTED = "rake_collected"
REFUND_ISSUED = "refund_issued"

_initialized = False
_enabled = False


def _ensure_client() -> bool:
    """Lazily configure the PostHog client once; return whether capture is live."""
    global _initialized, _enabled
    if _initialized:
        return _enabled
    _initialized = True
    settings = get_settings()
    if not settings.posthog_api_key:
        return False
    try:
        import posthog

        posthog.api_key = settings.posthog_api_key
        posthog.host = settings.posthog_host
        _enabled = True
    except Exception as exc:  # noqa: BLE001 — never let analytics setup break boot
        log.warning("analytics.init_failed", error=str(exc))
        _enabled = False
    return _enabled


def capture(
    event: str,
    distinct_id: uuid.UUID | str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Capture one server-side event. No-op when unconfigured; never raises."""
    if not _ensure_client():
        return
    try:
        import posthog

        props = dict(properties or {})
        settings = get_settings()
        if settings.release:
            props.setdefault("release", settings.release)
        posthog.capture(event, distinct_id=str(distinct_id), properties=props)
    except Exception as exc:  # noqa: BLE001 — telemetry must not break a money path
        log.warning("analytics.capture_failed", event=event, error=str(exc))


def reset_for_tests() -> None:
    """Force re-initialization (used when a test flips the config)."""
    global _initialized, _enabled
    _initialized = False
    _enabled = False
