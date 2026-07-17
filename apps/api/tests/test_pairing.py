"""Duel-forecast pairing math (pure). No DB, no I/O."""

from __future__ import annotations

import math

import pytest

from moneymatch_api.services import pairing


def test_normal_cdf_known_points():
    assert pairing.normal_cdf(0.0) == pytest.approx(0.5)
    assert pairing.normal_cdf(1.0) == pytest.approx(0.8413, abs=1e-3)
    assert pairing.normal_cdf(-1.0) == pytest.approx(0.1587, abs=1e-3)


def test_forecast_equal_players_is_a_coin_flip():
    assert pairing.forecast_prob(1.0, 0.2, 1.0, 0.2) == pytest.approx(0.5)


def test_forecast_higher_mean_favored():
    p = pairing.forecast_prob(1.3, 0.2, 1.0, 0.2)
    assert p > 0.5
    # Symmetry: P(a beats b) == 1 − P(b beats a).
    assert p == pytest.approx(1.0 - pairing.forecast_prob(1.0, 0.2, 1.3, 0.2))


def test_forecast_zero_variance_is_deterministic():
    assert pairing.forecast_prob(1.5, 0.0, 1.0, 0.0) == 1.0
    assert pairing.forecast_prob(1.0, 0.0, 1.5, 0.0) == 0.0
    assert pairing.forecast_prob(1.0, 0.0, 1.0, 0.0) == 0.5


def test_forecast_matches_closed_form_phi():
    mu_a, sig_a, mu_b, sig_b = 1.4, 0.3, 1.0, 0.4
    denom = math.sqrt(sig_a**2 + sig_b**2)
    expected = pairing.normal_cdf((mu_a - mu_b) / denom)
    assert pairing.forecast_prob(mu_a, sig_a, mu_b, sig_b) == pytest.approx(expected)


def test_widening_ladder_steps_up_with_wait():
    # 0.05 for 0–30s → 0.10 to 2min → 0.15 to 5min (constants.PAIRING_WIDENING_LADDER).
    assert pairing.band_width_for_age(0) == 0.05
    assert pairing.band_width_for_age(30) == 0.05
    assert pairing.band_width_for_age(31) == 0.10
    assert pairing.band_width_for_age(120) == 0.10
    assert pairing.band_width_for_age(200) == 0.15
    assert pairing.band_width_for_age(300) == 0.15
    # Past the last stage it holds at the widest w (service offers cancel).
    assert pairing.band_width_for_age(10_000) == 0.15


def test_widening_exhaustion_flag():
    assert not pairing.is_widening_exhausted(299)
    assert pairing.is_widening_exhausted(301)


def test_effective_w_uses_the_wider_of_two_tickets():
    # Fresh incoming (age 0 → 0.05) vs a ticket that has waited 3 min (→ 0.15).
    assert pairing.effective_w(0, 180) == 0.15


def test_eligibility_window():
    # A 52% duel is inside a 0.05 band; a 60% duel is not.
    assert pairing.is_forecast_eligible(0.52, 0.05)
    assert not pairing.is_forecast_eligible(0.60, 0.05)
    # But a 60% duel becomes eligible once the band has widened to 0.15.
    assert pairing.is_forecast_eligible(0.60, 0.15)


def test_lopsided_duel_never_eligible_even_at_widest_band():
    # A crafted 85/15 mismatch stays outside even the widest offered band.
    p = pairing.forecast_prob(2.0, 0.2, 1.0, 0.2)
    assert p > 0.5 + 0.15
    assert not pairing.is_forecast_eligible(p, pairing.band_width_for_age(10_000))


def test_chess_band_grows_and_caps():
    assert pairing.chess_band(0) == 100
    assert pairing.chess_band(10) == 220  # 100 + 10*12
    assert pairing.chess_band(10_000) == 800  # capped


def test_chess_eligibility_within_band():
    assert pairing.is_chess_eligible(1500, 1580, band=100)
    assert not pairing.is_chess_eligible(1500, 1700, band=100)


def test_composite_prefers_closer_means_then_steadier_variance():
    # Candidate 1 closer in mean than candidate 2 → lower (better) score.
    close = pairing.composite_score(1.0, 0.2, 1.05, 0.2)
    far = pairing.composite_score(1.0, 0.2, 1.4, 0.2)
    assert close < far

    # Equal means: the steadier (closer variance) candidate scores lower.
    steady = pairing.composite_score(1.0, 0.2, 1.0, 0.22)
    swingy = pairing.composite_score(1.0, 0.2, 1.0, 0.6)
    assert steady < swingy


def test_composite_folds_in_rating_distance_when_present():
    near = pairing.composite_score(1.0, 0.2, 1.0, 0.2, rating_a=1500, rating_b=1520)
    wide = pairing.composite_score(1.0, 0.2, 1.0, 0.2, rating_a=1500, rating_b=2000)
    assert wide > near
