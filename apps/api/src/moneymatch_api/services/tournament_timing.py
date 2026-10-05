"""Tournament timings, with optional environment overrides for testing.

The defaults live in `constants.py` (a tournament runs 3 h from when its
second player joins, then a per-game grace period before the final poll).
Setting these env vars shortens them, which is how you run a whole tournament
locally in minutes:

    TOURNAMENT_WINDOW_SECONDS=900
    TOURNAMENT_GRACE_SECONDS=60        # one grace period for every game

The duration only affects tournaments that *start* after it is set (the end is
stamped when the second player joins); the grace period is read at settle time.
"""

from __future__ import annotations

from ..config import get_settings
from ..constants import TOURNAMENT_GRACE_SECONDS, TOURNAMENT_WINDOW_SECONDS


def join_window_seconds() -> int:
    """How long a started tournament keeps taking players. For now, the whole
    run (up to the field size); a shorter join timer is planned."""
    return duration_seconds()


def duration_seconds() -> int:
    override = get_settings().tournament_window_seconds
    return override if override is not None else TOURNAMENT_WINDOW_SECONDS


def grace_seconds(game: str) -> int:
    override = get_settings().tournament_grace_seconds
    return override if override is not None else TOURNAMENT_GRACE_SECONDS.get(game, 0)
