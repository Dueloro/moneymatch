"""The one source of 'what time is it'. Every service, engine, worker and router used
to define its own private ``_now()`` returning ``datetime.now(UTC)``.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now() -> datetime:
    """The current instant, timezone-aware in UTC."""
    return datetime.now(UTC)
