"""Elo expectancy + chess bracket labels (ported from the PoC)."""

from __future__ import annotations

import pytest

from moneymatch_api.schemas.profile import FormatStat, ProfileSnapshot
from moneymatch_api.services import skill_rating


def _profile(**formats: int) -> ProfileSnapshot:
    return ProfileSnapshot(
        username="p",
        display_name="p",
        url="https://lichess.org/@/p",
        link_method="username",
        win_rate=0.5,
        total_games=100,
        formats=[FormatStat(speed=s, rating=r, games=50) for s, r in formats.items()],
    )


def test_win_expectancy_is_half_at_equal_ratings():
    assert skill_rating.win_expectancy(1500, 1500) == pytest.approx(0.5)


def test_win_expectancy_favors_higher_rating():
    assert skill_rating.win_expectancy(1700, 1500) > 0.5
    assert skill_rating.win_expectancy(1300, 1500) < 0.5


def test_rating_for_speed_prefers_exact_then_most_played_then_default():
    p = _profile(blitz=1600, rapid=1700)
    assert skill_rating.rating_for_speed(p, "blitz") == 1600
    # Unknown speed → most-played format (both 50 games → a max wins).
    assert skill_rating.rating_for_speed(p, "bullet") in (1600, 1700)
    # No formats at all → reference rating.
    assert skill_rating.rating_for_speed(_profile(), "blitz") == 1500


def test_make_bracket_labels_even_and_lopsided():
    assert skill_rating.make_bracket(1500, 1500).label == "Even match"
    assert skill_rating.make_bracket(1900, 1400).label == "You're favored"
    assert skill_rating.make_bracket(1400, 1900).label == "Reach"


def test_make_bracket_band_and_quality():
    b = skill_rating.make_bracket(1500, 1500, band=100)
    assert (b.band_low, b.band_high) == (1400, 1600)
    assert b.match_quality == 1.0  # coin-flip is maximum quality
