"""A quoted bar must be a number a human could actually hit.

The report was a hard chess pool advertising **"-6 moves or fewer"**. Three
separate things had to be wrong for that to reach a card, and each is pinned
here:

1. The bar sat at `mu - k*sigma` on a **normal** distribution. Once the spread
   approaches the mean, that expression walks off the bottom of the scale. Game
   length is strictly positive and right-skewed, so it is a lognormal.
2. The spread was the **raw sample** one. From 9 games it measured 18.1 moves
   around a mean of 25.7, versus a population figure near 12.4. A spread that
   inflated throws the bar much too far from the centre.
3. Nothing **floored** the result, so an impossible number was quoted rather
   than caught.

The population figures come from 4,526 sampled decisive Lichess games; see
`services/skill_prior.py` for the table and the fit.
"""

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

pytestmark = pytest.mark.nodb

MOVES_INC = METRIC_BAR_INCREMENT["chess_moves"]
FLOOR = metric_floor("chess_moves")

# The exact metric model behind the screenshot.
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


def _corrected(mu: float, sigma: float, n: int, rating: float | None):
    mu2, sigma2 = skill_prior.shrink(
        mu, sigma, n, skill_prior.prior_for("chess_moves", rating)
    )
    return mu2, fairness.effective_sigma(sigma2, MOVES_INC)


# --------------------------------------------------------------------------- #
# The reported bug.
# --------------------------------------------------------------------------- #


#: The hard tier's old multiplier, kept only to reproduce the reported bar.
OLD_HARD_K = 1.75


def test_the_screenshot_no_longer_quotes_a_negative_bar():
    mu, sigma, n = SCREENSHOT
    # The old placement, written out: mu - k*sigma on a normal, no floor.
    old = fairness.round_to_increment(mu - OLD_HARD_K * sigma, MOVES_INC)
    assert old == -6.0  # exactly what shipped: "-6 moves or fewer"

    new = _bar(*_corrected(mu, sigma, n, SCREENSHOT_RATING), "hard")
    assert new >= FLOOR
    assert 8 <= new <= 20, new


def test_every_tier_is_a_playable_number_for_the_screenshot_player():
    mu, sigma = _corrected(*SCREENSHOT, SCREENSHOT_RATING)
    bars = [_bar(mu, sigma, d) for d in ("easy", "medium", "hard")]
    assert all(b >= FLOOR for b in bars), bars
    assert bars == sorted(bars, reverse=True)  # harder asks for fewer moves
    assert len(set(bars)) == 3  # and the tiers stay distinct


# --------------------------------------------------------------------------- #
# The property that makes it impossible, not merely unlikely.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mu", [4.0, 12.0, 25.7, 40.0, 90.0])
@pytest.mark.parametrize("sigma", [0.5, 6.0, 18.0, 40.0, 200.0])
def test_a_positive_metric_can_never_quote_a_non_positive_bar(mu, sigma):
    """Including spreads far wider than the mean, which is where normal breaks."""
    for difficulty in POOL_DIFFICULTY_K:
        assert _bar(mu, sigma, difficulty) >= FLOOR, (mu, sigma, difficulty)


def test_the_floor_alone_would_not_have_been_enough():
    """Guards the premise: clamping a broken number is not the same as fixing it.

    A floor turns "-6 moves" into "2 moves", which is legal and still
    unwinnable. The distribution has to be right for the bar to be *reasonable*,
    not merely non-negative.
    """
    mu, sigma = SCREENSHOT[0], SCREENSHOT[1]
    clamped = fairness.personal_bar(mu, sigma, OLD_HARD_K, MOVES_INC, True, floor=FLOOR)
    assert clamped == FLOOR  # legal, and nobody has ever won a rated game in 2

    honest = _bar(*_corrected(*SCREENSHOT, SCREENSHOT_RATING), "hard")
    assert honest > 4 * clamped


def test_a_rate_metric_is_untouched_by_the_change():
    """cs2_kd_ratio is not positive-support, so it keeps the normal placement."""
    assert positive_support("cs2_kd_ratio") is False
    assert fairness.personal_bar(1.2, 0.3, 1.0, 0.05, False) == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# Bar placement and clear probability must agree, or no room can form.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("difficulty", list(POOL_DIFFICULTY_K))
def test_the_advertised_rate_matches_the_bar_actually_quoted(difficulty):
    mu, sigma = _corrected(*SCREENSHOT, SCREENSHOT_RATING)
    k = POOL_DIFFICULTY_K[difficulty]
    bar = _bar(mu, sigma, difficulty)
    shown = fairness.clear_prob(bar, mu, sigma, True, positive=True)
    # Whole-move rounding is the only permitted source of drift.
    assert shown == pytest.approx(fairness.p_target_for_k(k), abs=0.05), difficulty


@pytest.mark.parametrize("difficulty", list(POOL_DIFFICULTY_K))
def test_a_room_still_composes_under_the_lognormal(difficulty):
    """The regression that produced rooms of one.

    A bar placed on one distribution and judged on another puts every member's
    implied clear probability outside the fair band, and the matcher rejects
    every group forever.
    """
    mu, sigma = _corrected(*SCREENSHOT, SCREENSHOT_RATING)
    k = POOL_DIFFICULTY_K[difficulty]
    bar = _bar(mu, sigma, difficulty)
    assert fairness.member_fair(
        bar, mu, sigma, fairness.p_target_for_k(k), True, positive=True
    ), difficulty


def test_judging_a_lognormal_bar_on_a_normal_is_what_breaks_composition():
    """The two are different answers, and the mismatch is what kills a room.

    A wide-spread player is where they diverge most. Judged consistently the
    member sits inside the fair band; judged on the wrong distribution the same
    player reads as far too likely to clear and the matcher rejects the group.
    """
    mu, sigma = 30.0, 40.0
    k = POOL_DIFFICULTY_K["hard"]
    p_target = fairness.p_target_for_k(k)
    bar = _bar(mu, sigma, "hard")

    assert fairness.member_fair(bar, mu, sigma, p_target, True, positive=True)
    assert not fairness.member_fair(bar, mu, sigma, p_target, True, positive=False)


# --------------------------------------------------------------------------- #
# Rating and shrinkage.
# --------------------------------------------------------------------------- #


def test_a_stronger_player_is_expected_to_play_longer_games():
    """The measured relationship: about one extra move per 100 rating points."""
    weak, _ = skill_prior.prior_for("chess_moves", 1000)
    strong, _ = skill_prior.prior_for("chess_moves", 2000)
    assert strong - weak == pytest.approx(10.0, abs=1.5)
    assert weak == pytest.approx(26.8, abs=1.5)  # observed 25.5


def test_rating_moves_the_bar_in_the_same_direction():
    beginner = _bar(*_corrected(30.0, 12.0, 5, 1000), "medium")
    expert = _bar(*_corrected(30.0, 12.0, 5, 2200), "medium")
    assert expert > beginner


def test_an_unreadable_rating_still_produces_a_sane_bar():
    """A missing rating must degrade, not throw or quote nonsense."""
    assert skill_prior.prior_for("chess_moves", None) is not None
    assert _bar(*_corrected(*SCREENSHOT, None), "hard") >= FLOOR


def test_a_metric_with_no_measured_prior_keeps_its_own_numbers():
    assert skill_prior.prior_for("cs2_kd_ratio", 1500) is None
    assert skill_prior.shrink(1.2, 0.3, 4, None) == (1.2, 0.3)


def test_shrinkage_pulls_a_thin_sample_toward_the_prior():
    mu, sigma, n = SCREENSHOT
    corrected_mu, corrected_sigma = skill_prior.shrink(
        mu, sigma, n, skill_prior.prior_for("chess_moves", SCREENSHOT_RATING)
    )
    assert corrected_sigma < sigma  # 18.1 was noise, not a real spread
    assert mu < corrected_mu  # pulled up toward the 1058-rated expectation


def test_a_long_record_keeps_its_own_numbers():
    """Shrinkage must fade, or a settled player is quoted someone else's bar."""
    prior = skill_prior.prior_for("chess_moves", 1058)
    mu, sigma = skill_prior.shrink(25.7, 18.1, 400, prior)
    assert mu == pytest.approx(25.7, abs=0.4)
    assert sigma == pytest.approx(18.1, abs=0.4)


def test_shrinkage_is_monotonic_in_sample_size():
    prior = skill_prior.prior_for("chess_moves", 1058)
    seen = [skill_prior.shrink(25.7, 18.1, n, prior)[0] for n in (1, 5, 20, 100, 500)]
    assert seen == sorted(seen, reverse=True)  # each step trusts you more


def test_no_record_at_all_falls_back_to_the_prior():
    prior = skill_prior.prior_for("chess_moves", 1500)
    assert skill_prior.shrink(0.0, 0.0, 0, prior) == prior


# --------------------------------------------------------------------------- #
# The fit, against the sample it came from.
# --------------------------------------------------------------------------- #

# band -> (games sampled, observed mean moves, observed sd)
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
    """The left tail is the only part of the fit a fewest-moves bar uses.

    Quantiles measured on the same 4,526 decisive games, at the tiers' rates.
    """
    _, observed_mu, observed_sd = OBSERVED[band]
    s2 = math.log(1 + (observed_sd / observed_mu) ** 2)
    m = math.log(observed_mu) - s2 / 2
    # 35% and 20% quantiles as actually observed, per band.
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
