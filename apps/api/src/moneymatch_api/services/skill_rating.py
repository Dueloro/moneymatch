"""Elo skill rating + bracketing for chess head-to-head.

Ported from `poc-reference/api/_lib/skill_rating.py` (11-migration-map §1): money
match is peer-to-peer, so this estimates strength to put chess players in a
rating band and to surface an honest "even match / reach" signal — it never sets
a payout line. Rake is not here anymore: it's config on each `MarketDef`
(`services/markets.py`) computed in integer basis points (`services/money_math`).

Chess `win_h2h` uses this Elo band as its forecast (Elo already *is* the
forecast); stat duels use the duel-forecast normal model in `services/pairing.py`.
"""

from __future__ import annotations

import math

from ..constants import CHESS_BASE_BAND
from ..schemas.play import Bracket
from ..schemas.profile import ProfileSnapshot

_REFERENCE_RATING = 1500


def rating_for_speed(profile: ProfileSnapshot, speed: str | None) -> int:
    """The user's rating in this time control, falling back sensibly."""
    for f in profile.formats:
        if f.speed == speed:
            return f.rating
    if profile.formats:
        # Use the most-played format as a stand-in.
        return max(profile.formats, key=lambda f: f.games).rating
    return profile.rating or _REFERENCE_RATING


def win_expectancy(your_rating: int, opp_rating: int) -> float:
    """Standard Elo expectancy that ``you`` beat ``opp`` (0..1)."""
    return 1.0 / (1.0 + math.pow(10, (opp_rating - your_rating) / 400))


def make_bracket(
    your_rating: int, opp_rating: int, band: int = CHESS_BASE_BAND
) -> Bracket:
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
