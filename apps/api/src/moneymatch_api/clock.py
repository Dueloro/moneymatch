"""The one source of 'what time is it'.

Every service, engine, worker and router used to define its own private
``_now()`` returning ``datetime.now(UTC)``. Identical, but twelve of them, so a
test that needed to freeze or advance time had to patch each module separately —
time was un-mockable in one place. Call ``clock.now()`` instead, and a single
``monkeypatch.setattr("moneymatch_api.clock.now", ...)`` freezes the whole
system at once.

Always timezone-aware UTC. The money path compares and stamps timestamps; a
naive datetime slipping in is a correctness bug, so this never returns one.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now() -> datetime:
    """The current instant, timezone-aware in UTC."""
    return datetime.now(UTC)
