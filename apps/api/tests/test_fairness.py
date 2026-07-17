"""Pool/tournament fairness math (pure). Personal bars, room composition,
dispersion caps, and first-N scoring — no DB, no I/O."""

from __future__ import annotations

import pytest

from moneymatch_api.services import fairness


def test_round_to_increment_is_deterministic():
    assert fairness.round_to_increment(1.63, 0.05) == 1.65
    assert fairness.round_to_increment(1.62, 0.05) == 1.60
    assert fairness.round_to_increment(72.4, 1.0) == 72.0
    # Same inputs → identical float (room-bar reproducibility).
    assert fairness.round_to_increment(1.626, 0.05) == fairness.round_to_increment(
        1.626, 0.05
    )


def test_personal_bar_is_mu_plus_k_sigma_rounded():
    # Medium (k=1.0): 1.50 + 1.0·0.30 = 1.80.
    assert fairness.personal_bar(1.50, 0.30, 1.0, 0.05) == 1.80
    # Easy (k=0.5): 1.50 + 0.15 = 1.65.
    assert fairness.personal_bar(1.50, 0.30, 0.5, 0.05) == 1.65
    # Hard (k=1.75): 1.50 + 0.525 = 2.025 → nearest 0.05 (half-to-even) = 2.00.
    assert fairness.personal_bar(1.50, 0.30, 1.75, 0.05) == 2.00


def test_room_bar_is_rounded_mean_of_bars():
    assert fairness.room_bar([1.70, 1.75, 1.80, 1.75], 0.05) == 1.75


def test_clear_prob_matches_p_target_when_bar_is_own_personal_bar():
    # A player graded against their own μ+σ bar clears at exactly 1 − Φ(1) ≈ 0.159.
    p = fairness.clear_prob(1.80, 1.50, 0.30)
    assert p == pytest.approx(fairness.p_target_for_k(1.0), abs=1e-3)


def test_composition_refuses_a_shark_and_a_hopeless_outlier():
    bar = 1.80
    p_target = fairness.p_target_for_k(1.0)  # medium
    fair_members = [(1.50, 0.30), (1.52, 0.28), (1.48, 0.31)]
    assert fairness.composition_ok(bar, fair_members, p_target)

    # A shark clears the room bar ~99% of the time → breaches the upper bound.
    assert not fairness.composition_ok(bar, [*fair_members, (2.50, 0.30)], p_target)
    # A hopeless outlier clears ~0.4% of the time → breaches the lower bound.
    assert not fairness.composition_ok(bar, [*fair_members, (1.00, 0.30)], p_target)


def test_spread_cap_rejects_wide_personal_bars():
    sigmas = [0.30, 0.30, 0.30]
    assert fairness.spread_ok([1.75, 1.80, 1.85], sigmas, 1.5)
    assert not fairness.spread_ok([1.50, 3.00, 1.80], sigmas, 1.5)


def test_dispersion_cap_rejects_a_lopsided_field():
    sigmas = [0.20, 0.20, 0.20]
    # Spread 0.16 ≤ cap·σ_pooled = 1.0·0.20 → fair.
    assert fairness.dispersion_ok([1.42, 1.50, 1.58], sigmas, 1.0)
    # Spread 1.0 far exceeds the cap → refused.
    assert not fairness.dispersion_ok([1.00, 1.50, 2.00], sigmas, 1.0)


def test_first_n_average_uses_earliest_not_best_or_latest():
    avg, count = fairness.first_n_average([1.2, 1.4, 1.6, 1.8], 3)
    assert count == 3
    # mean of the first three (1.2,1.4,1.6) = 1.4 — not best-of, not latest.
    assert avg == pytest.approx(1.4)


def test_first_n_average_none_when_no_matches():
    assert fairness.first_n_average([], 3) == (None, 0)


def test_member_fair_bounds():
    p_target = fairness.p_target_for_k(1.0)
    lo, hi = fairness.composition_bounds(p_target)
    assert lo == pytest.approx(p_target / 2)
    assert hi == pytest.approx(min(2 * p_target, 0.5))
