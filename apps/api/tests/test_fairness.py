"""Pool/tournament fairness math (pure). Personal bars, room composition, and
dispersion caps — no DB, no I/O.
"""

from __future__ import annotations

import pytest

from moneymatch_api.services import fairness


def test_round_to_increment_is_deterministic():
    assert fairness.round_to_increment(1.63, 0.05) == 1.65
    assert fairness.round_to_increment(1.62, 0.05) == 1.60
    assert fairness.round_to_increment(72.4, 1.0) == 72.0
    assert fairness.round_to_increment(1.626, 0.05) == fairness.round_to_increment(
        1.626, 0.05
    )


def test_personal_bar_is_mu_plus_k_sigma_rounded():
    assert fairness.personal_bar(1.50, 0.30, 1.0, 0.05) == 1.80
    assert fairness.personal_bar(1.50, 0.30, 0.5, 0.05) == 1.65
    assert fairness.personal_bar(1.50, 0.30, 1.75, 0.05) == 2.00


def test_room_bar_is_rounded_mean_of_bars():
    assert fairness.room_bar([1.70, 1.75, 1.80, 1.75], 0.05) == 1.75


def test_clear_prob_matches_p_target_when_bar_is_own_personal_bar():
    p = fairness.clear_prob(1.80, 1.50, 0.30)
    assert p == pytest.approx(fairness.p_target_for_k(1.0), abs=1e-3)


def test_composition_refuses_a_shark_and_a_hopeless_outlier():
    bar = 1.80
    p_target = fairness.p_target_for_k(1.0)
    fair_members = [(1.50, 0.30), (1.52, 0.28), (1.48, 0.31)]
    assert fairness.composition_ok(bar, fair_members, p_target)

    assert not fairness.composition_ok(bar, [*fair_members, (2.50, 0.30)], p_target)
    assert not fairness.composition_ok(bar, [*fair_members, (1.00, 0.30)], p_target)


def test_spread_cap_rejects_wide_personal_bars():
    sigmas = [0.30, 0.30, 0.30]
    assert fairness.spread_ok([1.75, 1.80, 1.85], sigmas, 1.5)
    assert not fairness.spread_ok([1.50, 3.00, 1.80], sigmas, 1.5)


def test_dispersion_cap_rejects_a_lopsided_field():
    sigmas = [0.20, 0.20, 0.20]
    assert fairness.dispersion_ok([1.42, 1.50, 1.58], sigmas, 1.0)
    assert not fairness.dispersion_ok([1.00, 1.50, 2.00], sigmas, 1.0)


def test_member_fair_bounds():
    p_target = fairness.p_target_for_k(1.0)
    lo, hi = fairness.composition_bounds(p_target)
    assert lo == pytest.approx(p_target / 2)
    assert hi == pytest.approx(min(2 * p_target, 0.5))
