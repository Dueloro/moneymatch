"""Skill rating + bracketing for money match.

Repurposed from the deprecated house-banked odds engine: money match is
peer-to-peer, so the engine's job is **pairing**, not pricing (overview §3.2).
It estimates a player's strength to put them in a rating band and to surface an
honest "you're well-matched / this is a reach" signal — it never sets a payout
line. Revenue is the fixed ``rake`` taken off the pot, defined here as a
per-objective parameter.
"""

from __future__ import annotations

import math

from _lib.schemas import Bracket, SkillProfile, Speed

# Fixed, disclosed rake taken off every pot. Higher-variance objectives carry a
# slightly higher rake. This is the only revenue — the house takes no position.
DEFAULT_RAKE = 0.10
RAKE_BY_KIND = {
    "win_h2h": 0.08,
    "win_under_moves": 0.12,
}

# Half-width of the rating band matchmaking searches within.
DEFAULT_BAND = 80
_REFERENCE_RATING = 1500


def rake_for(kind: str) -> float:
    return RAKE_BY_KIND.get(kind, DEFAULT_RAKE)


def rating_for_speed(profile: SkillProfile, speed: Speed) -> int:
    """The user's rating in this time control, falling back sensibly."""
    for f in profile.formats:
        if f.speed == speed:
            return f.rating
    if profile.formats:
        # Use the most-played format as a stand-in.
        return max(profile.formats, key=lambda f: f.games).rating
    return _REFERENCE_RATING


def win_expectancy(your_rating: int, opp_rating: int) -> float:
    """Standard Elo expectancy that ``you`` beat ``opp`` (0..1)."""
    return 1.0 / (1.0 + math.pow(10, (opp_rating - your_rating) / 400))


def make_bracket(your_rating: int, opp_rating: int, band: int = DEFAULT_BAND) -> Bracket:
    """Describe how fair a pairing is, for honest pre-match disclosure."""
    expe = win_expectancy(your_rating, opp_rating)
    # Quality is 1.0 at a coin-flip and decays as the matchup gets lopsided.
    quality = round(1.0 - 2.0 * abs(expe - 0.5), 2)

    if expe >= 0.62:
        label = "You're favored"
    elif expe >= 0.55:
        label = "Slight edge to you"
    elif expe <= 0.38:
        label = "Reach"
    elif expe <= 0.45:
        label = "Slight underdog"
    else:
        label = "Even match"

    return Bracket(
        your_rating=your_rating,
        band_low=your_rating - band,
        band_high=your_rating + band,
        match_quality=quality,
        label=label,
    )
