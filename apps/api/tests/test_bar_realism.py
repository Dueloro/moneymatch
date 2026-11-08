"""A quoted bar must be a number a human could actually hit."""

from __future__ import annotations

import math

import pytest

from moneymatch_api.constants import (
    METRIC_BAR_INCREMENT,
    POOL_DIFFICULTY_K,
    metric_floor,
    positive_support,
)
from moneymatch_api.services import fairness, skill_prior

from .factories import chess_moves_corrected

pytestmark = pytest.mark.nodb

MOVES_INC = METRIC_BAR_INCREMENT["chess_moves"]
FLOOR = metric_floor("chess_moves")

SCREENSHOT = (25.663938360574466, 18.057372079352717, 9)
SCREENSHOT_RATING = 1058.0


def _bar(mu: float, sigma: float, difficulty: str) -> float:
    return fairness.personal_bar(
        mu,
        sigma,
        POOL_DIFFICULTY_K[difficulty],
        MOVES_INC,
        True,
        positive=True,
        floor=FLOOR,
    )


OLD_HARD_K = 1.75


def test_the_screenshot_no_longer_quotes_a_negative_bar():
    mu, sigma, n = SCREENSHOT
    old = fairness.round_to_increment(mu - OLD_HARD_K * sigma, MOVES_INC)
    assert old == -6.0

    new = _bar(*chess_moves_corrected(mu, sigma, n, SCREENSHOT_RATING), "hard")
    assert new >= FLOOR
    assert 8 <= new <= 20, new


def test_every_tier_is_a_playable_number_for_the_screenshot_player():
    mu, sigma = chess_moves_corrected(*SCREENSHOT, SCREENSHOT_RATING)
    bars = [_bar(mu, sigma, d) for d in ("easy", "medium", "hard")]
    assert all(b >= FLOOR for b in bars), bars
    assert bars == sorted(bars, reverse=True)
    assert len(set(bars)) == 3


@pytest.mark.parametrize("mu", [4.0, 12.0, 25.7, 40.0, 90.0])
@pytest.mark.parametrize("sigma", [0.5, 6.0, 18.0, 40.0, 200.0])
def test_a_positive_metric_can_never_quote_a_non_positive_bar(mu, sigma):
    for difficulty in POOL_DIFFICULTY_K:
        assert _bar(mu, sigma, difficulty) >= FLOOR, (mu, sigma, difficulty)


def test_the_floor_alone_would_not_have_been_enough():
    mu, sigma = SCREENSHOT[0], SCREENSHOT[1]
    clamped = fairness.personal_bar(mu, sigma, OLD_HARD_K, MOVES_INC, True, floor=FLOOR)
    assert clamped == FLOOR

    honest = _bar(*chess_moves_corrected(*SCREENSHOT, SCREENSHOT_RATING), "hard")
    assert honest > 4 * clamped


def test_a_rate_metric_is_untouched_by_the_change():
    assert positive_support("chess_accuracy") is False
    assert fairness.personal_bar(1.2, 0.3, 1.0, 0.05, False) == pytest.approx(1.5)


@pytest.mark.parametrize("difficulty", list(POOL_DIFFICULTY_K))
def test_the_advertised_rate_matches_the_bar_actually_quoted(difficulty):
    mu, sigma = chess_moves_corrected(*SCREENSHOT, SCREENSHOT_RATING)
    k = POOL_DIFFICULTY_K[difficulty]
    bar = _bar(mu, sigma, difficulty)
    shown = fairness.clear_prob(bar, mu, sigma, True, positive=True)
    # Whole-move rounding is the only permitted source of drift.
    assert shown == pytest.approx(fairness.p_target_for_k(k), abs=0.05), difficulty


@pytest.mark.parametrize("difficulty", list(POOL_DIFFICULTY_K))
def test_a_room_still_composes_under_the_lognormal(difficulty):
    mu, sigma = chess_moves_corrected(*SCREENSHOT, SCREENSHOT_RATING)
    k = POOL_DIFFICULTY_K[difficulty]
    bar = _bar(mu, sigma, difficulty)
    assert fairness.member_fair(
        bar, mu, sigma, fairness.p_target_for_k(k), True, positive=True
    ), difficulty


def test_judging_a_lognormal_bar_on_a_normal_is_what_breaks_composition():
    mu, sigma = 30.0, 40.0
    k = POOL_DIFFICULTY_K["hard"]
    p_target = fairness.p_target_for_k(k)
    bar = _bar(mu, sigma, "hard")

    assert fairness.member_fair(bar, mu, sigma, p_target, True, positive=True)
    assert not fairness.member_fair(bar, mu, sigma, p_target, True, positive=False)


def test_a_stronger_player_is_expected_to_play_longer_games():
    weak, _ = skill_prior.prior_for("chess_moves", 1000)
    strong, _ = skill_prior.prior_for("chess_moves", 2000)
    assert strong - weak == pytest.approx(10.0, abs=1.5)
    assert weak == pytest.approx(26.8, abs=1.5)


def test_rating_moves_the_bar_in_the_same_direction():
    beginner = _bar(*chess_moves_corrected(30.0, 12.0, 5, 1000), "medium")
    expert = _bar(*chess_moves_corrected(30.0, 12.0, 5, 2200), "medium")
    assert expert > beginner


def test_an_unreadable_rating_still_produces_a_sane_bar():
    assert skill_prior.prior_for("chess_moves", None) is not None
    assert _bar(*chess_moves_corrected(*SCREENSHOT, None), "hard") >= FLOOR


def test_a_metric_with_no_measured_prior_keeps_its_own_numbers():
    assert skill_prior.prior_for("chess_accuracy", 1500) is None
    assert skill_prior.shrink(1.2, 0.3, 4, None) == (1.2, 0.3)


def test_shrinkage_pulls_a_thin_sample_toward_the_prior():
    mu, sigma, n = SCREENSHOT
    corrected_mu, corrected_sigma = skill_prior.shrink(
        mu, sigma, n, skill_prior.prior_for("chess_moves", SCREENSHOT_RATING)
    )
    assert corrected_sigma < sigma
    assert mu < corrected_mu


def test_a_long_record_keeps_its_own_numbers():
    prior = skill_prior.prior_for("chess_moves", 1058)
    mu, sigma = skill_prior.shrink(25.7, 18.1, 400, prior)
    assert mu == pytest.approx(25.7, abs=0.4)
    assert sigma == pytest.approx(18.1, abs=0.4)


def test_shrinkage_is_monotonic_in_sample_size():
    prior = skill_prior.prior_for("chess_moves", 1058)
    seen = [skill_prior.shrink(25.7, 18.1, n, prior)[0] for n in (1, 5, 20, 100, 500)]
    assert seen == sorted(seen, reverse=True)


def test_no_record_at_all_falls_back_to_the_prior():
    prior = skill_prior.prior_for("chess_moves", 1500)
    assert skill_prior.shrink(0.0, 0.0, 0, prior) == prior


OBSERVED = {
    1000: (158, 25.5, 11.7),
    1200: (273, 29.4, 11.8),
    1400: (673, 32.0, 12.0),
    1600: (1107, 32.3, 11.5),
    1800: (1318, 34.4, 11.7),
    2000: (698, 37.7, 12.5),
    2200: (248, 39.1, 13.4),
}


@pytest.mark.parametrize("band", sorted(OBSERVED))
def test_the_prior_reproduces_the_sample_it_was_fitted_to(band):
    _, observed_mu, observed_sd = OBSERVED[band]
    mu, sigma = skill_prior.prior_for("chess_moves", float(band))
    assert mu == pytest.approx(observed_mu, abs=1.5), band
    assert sigma == pytest.approx(observed_sd, abs=1.5), band


@pytest.mark.parametrize("band", sorted(OBSERVED))
def test_the_lognormal_low_tail_matches_the_sample(band):
    _, observed_mu, observed_sd = OBSERVED[band]
    s2 = math.log(1 + (observed_sd / observed_mu) ** 2)
    m = math.log(observed_mu) - s2 / 2
    empirical = {
        1000: (21, 16),
        1200: (24, 20),
        1400: (26, 23),
        1600: (27, 23),
        1800: (30, 25),
        2000: (32, 27),
        2200: (33, 28),
    }[band]
    for z, actual in zip((0.385, 0.842), empirical, strict=True):
        predicted = math.exp(m - z * math.sqrt(s2))
        assert predicted == pytest.approx(actual, abs=2.5), (band, z)
