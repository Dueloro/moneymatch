"""Difficulty must run the right way for a fewest-is-better stat.

`chess_moves` is won by the *smaller* number, but the pool engine's bar was
`µ + k·σ`, which assumes bigger is better. A "hard" chess pool therefore asked
you to take *more* moves than an easy one, which is backwards.

Two things are pinned here: the direction, and the fact that three difficulty
tiers actually produce three different bars.
"""

from __future__ import annotations

import pytest

from moneymatch_api.constants import (
    METRIC_BAR_INCREMENT,
    POOL_DIFFICULTY_K,
    lower_is_better,
)
from moneymatch_api.services import fairness

pytestmark = pytest.mark.nodb

MOVES_INC = METRIC_BAR_INCREMENT["chess_moves"]


def _bars(mu: float, sigma: float, increment: float, low: bool) -> list[float]:
    """Bars as the engine quotes them: the spread is floored once, up front."""
    spread = fairness.effective_sigma(sigma, increment)
    return [
        fairness.personal_bar(mu, spread, POOL_DIFFICULTY_K[d], increment, low)
        for d in ("easy", "medium", "hard")
    ]


def test_chess_moves_is_registered_as_fewest_wins():
    assert lower_is_better("chess_moves") is True
    assert lower_is_better("cs2_kd_ratio") is False


def test_harder_asks_for_fewer_moves():
    easy, medium, hard = _bars(28.0, 8.0, MOVES_INC, True)
    assert easy > medium > hard, (easy, medium, hard)


def test_harder_still_asks_for_more_of_a_rate_stat():
    easy, medium, hard = _bars(1.20, 0.30, 0.05, False)
    assert easy < medium < hard, (easy, medium, hard)


def test_tiers_stay_distinct_even_on_a_tight_sample():
    """The regression that made three cards show the same number.

    With sigma 0.5 and a bar quoted in whole moves, k·sigma is under one move
    at every tier, so all three rounded to 15 and the page showed one card
    printed three times.
    """
    bars = _bars(15.48, 0.5, MOVES_INC, True)
    assert len(set(bars)) == 3, bars
    assert bars == sorted(bars, reverse=True)


def test_clearing_a_fewest_metric_means_coming_in_under_the_bar():
    # A player who averages 28 moves, against a bar of 24.
    assert fairness.clear_prob(24.0, 28.0, 8.0, True) > 0.25
    # The same numbers read as "bigger is better" would be the complement.
    assert fairness.clear_prob(24.0, 28.0, 8.0, False) == pytest.approx(
        1 - fairness.clear_prob(24.0, 28.0, 8.0, True)
    )


def test_a_realistic_sample_lands_near_the_design_rates():
    """Difficulty means the same thing in both directions: 1 − Φ(k).

    The expectation is derived from `k` rather than written down, so retuning a
    tier changes the bar and its advertised rate together instead of quietly
    putting the two out of step.
    """
    mu, sigma = 28.0, 8.0
    spread = fairness.effective_sigma(sigma, MOVES_INC)
    for difficulty, k in POOL_DIFFICULTY_K.items():
        bar = fairness.personal_bar(mu, spread, k, MOVES_INC, True)
        assert fairness.clear_prob(bar, mu, spread, True) == pytest.approx(
            fairness.p_target_for_k(k), abs=0.06
        ), difficulty


def test_a_room_composes_for_a_tight_spread_player():
    """The regression that stopped practice opponents ever joining a room.

    The bar was placed with a floored spread while the fair band was judged with
    the raw one, so a tight-spread player's implied clear probability sat far
    outside the band and no room could ever form. Flooring once, at the model,
    keeps the two in agreement.
    """
    mu, raw = 16.05, 0.5
    spread = fairness.effective_sigma(raw, MOVES_INC)
    for difficulty in ("easy", "medium", "hard"):
        k = POOL_DIFFICULTY_K[difficulty]
        bar = fairness.personal_bar(mu, spread, k, MOVES_INC, True)
        assert fairness.member_fair(
            bar, mu, spread, fairness.p_target_for_k(k), True
        ), difficulty


def test_zero_spread_degenerates_sanely():
    # No variance: you clear iff your average already beats the bar.
    assert fairness.clear_prob(20.0, 18.0, 0.0, True) == 1.0
    assert fairness.clear_prob(20.0, 22.0, 0.0, True) == 0.0
