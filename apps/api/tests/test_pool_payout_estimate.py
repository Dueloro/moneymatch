"""The estimate is a share model, `(1 − rake) / clear_rate`, which divides by the
clear rate, so a very hard tier divided by a number near zero and the card
advertised **$225,000 on a $25 entry**.
"""

from __future__ import annotations

import pytest

from moneymatch_api.constants import (
    METRIC_BAR_INCREMENT,
    POOL_DIFFICULTY_K,
    POOL_ROOM_SIZE,
)
from moneymatch_api.services import fairness, money_math

pytestmark = pytest.mark.nodb

ENTRY = 2500
RAKE_BPS = money_math.DEFAULT_RAKE_BPS


def _est(clear_rate: float, entry: int = ENTRY) -> int:
    bps = money_math.pool_multiplier_estimate_bps(clear_rate, room_size=POOL_ROOM_SIZE)
    return entry * bps // 10_000


def _full_pot_take_home(entry: int = ENTRY) -> int:
    pot = entry * POOL_ROOM_SIZE
    return pot - (pot * RAKE_BPS // 10_000)


def test_the_screenshot_case_is_the_pot_not_a_fantasy():
    assert _est(0.0) == _full_pot_take_home() == 9000


def test_no_clear_rate_can_advertise_more_than_the_pot():
    cap = _full_pot_take_home()
    for rate in (1.0, 0.5, 0.31, 0.16, 0.04, 0.004, 0.0001, 0.0):
        assert _est(rate) <= cap, rate


def test_the_estimate_still_rises_as_a_tier_gets_harder():
    assert _est(1.0) < _est(0.31) < _est(0.16)


def test_everyone_clearing_returns_your_stake_less_rake():
    # A whole room clears, so the pot divides four ways and only rake is lost.
    assert _est(1.0) == ENTRY - (ENTRY * RAKE_BPS // 10_000)


def test_the_cap_tracks_room_size_rather_than_being_hardcoded():
    two = money_math.pool_multiplier_estimate_bps(0.0, room_size=2)
    eight = money_math.pool_multiplier_estimate_bps(0.0, room_size=8)
    assert eight == 4 * two


def test_an_empty_room_cannot_pay_anything():
    assert money_math.pool_multiplier_estimate_bps(0.0, room_size=0) == 0


def test_three_difficulty_tiers_never_collapse_onto_one_number():
    inc = METRIC_BAR_INCREMENT["chess_moves"]
    for mu in (15.48, 16.05, 22.0, 31.7):
        spread = fairness.effective_sigma(0.5, inc)
        bars = [
            fairness.personal_bar(mu, spread, POOL_DIFFICULTY_K[d], inc, True)
            for d in ("easy", "medium", "hard")
        ]
        assert len(set(bars)) == 3, (mu, bars)
        assert bars == sorted(bars, reverse=True), (mu, bars)
