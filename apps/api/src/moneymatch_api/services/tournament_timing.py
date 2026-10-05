"""Tournament timings, with optional environment overrides for testing.

The defaults live in `constants.py` (joins open 1 h, tournament runs 3 h, a
per-game grace period before the final poll). Setting any of these env vars
shortens them, which is how you run a whole tournament locally in minutes:

    TOURNAMENT_JOIN_WINDOW_SECONDS=300
    TOURNAMENT_WINDOW_SECONDS=900
    TOURNAMENT_GRACE_SECONDS=60        # one grace period for every game

A timing only affects tournaments *opened* after it is set (join close and end
are stamped on the row when it opens); the grace period is read at settle time.
"""

from __future__ import annotations

from ..config import get_settings
from ..constants import (
    TOURNAMENT_GRACE_SECONDS,
    TOURNAMENT_JOIN_WINDOW_SECONDS,
    TOURNAMENT_WINDOW_SECONDS,
)


def join_window_seconds() -> int:
    override = get_settings().tournament_join_window_seconds
    return override if override is not None else TOURNAMENT_JOIN_WINDOW_SECONDS


def duration_seconds() -> int:
    override = get_settings().tournament_window_seconds
    return override if override is not None else TOURNAMENT_WINDOW_SECONDS


def grace_seconds(game: str) -> int:
    override = get_settings().tournament_grace_seconds
    return override if override is not None else TOURNAMENT_GRACE_SECONDS.get(game, 0)
