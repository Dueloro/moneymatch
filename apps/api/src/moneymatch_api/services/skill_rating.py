"""Elo skill rating for chess head-to-head."""

from __future__ import annotations

import math

from ..schemas.profile import ProfileSnapshot

_REFERENCE_RATING = 1500


def rating_for_speed(profile: ProfileSnapshot, speed: str | None) -> int:
    """The user's rating in this time control, falling back sensibly."""
    for f in profile.formats:
        if f.speed == speed:
            return f.rating
    if profile.formats:
        return max(profile.formats, key=lambda f: f.games).rating
    return profile.rating or _REFERENCE_RATING


def win_expectancy(your_rating: int, opp_rating: int) -> float:
    return 1.0 / (1.0 + math.pow(10, (opp_rating - your_rating) / 400))
