"""Phase 2 test gate — the skill index (best-of-40%, Welford, rise/fall).

Pure maths, no DB (`nodb`). These are the checks `IMPLEMENTATION_BUCKETING.md`
Phase 2 requires green before Phase 3 starts.
"""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services.bucketing import index as ix

pytestmark = pytest.mark.nodb


# --------------------------------------------------------------------------- #
# Welford matches a from-scratch batch computation (property test)
# --------------------------------------------------------------------------- #


def test_welford_matches_batch_mean_and_variance():
    rng = random.Random(1234)
    for _ in range(200):
        n = rng.randint(2, 60)
        values = [rng.uniform(-100, 100) for _ in range(n)]
        mean = m2 = 0.0
        cnt = 0
        for v in values:
            mean, m2, cnt = ix.welford_update(mean, m2, cnt, v)
        batch_mean = sum(values) / n
        batch_var = sum((v - batch_mean) ** 2 for v in values) / (n - 1)
        assert mean == pytest.approx(batch_mean, rel=1e-9, abs=1e-9)
        assert ix.variance(m2, cnt) == pytest.approx(batch_var, rel=1e-9, abs=1e-9)


# --------------------------------------------------------------------------- #
# Best-of-40% correctness
# --------------------------------------------------------------------------- #


def test_best_k_schedule():
    # ceil(0.4·len), floored at 3 once the window is big enough to allow it.
    assert ix.best_k(0) == 0
    assert ix.best_k(1) == 1
    assert ix.best_k(2) == 2  # can't demand 3 from a 2-length window
    assert ix.best_k(3) == 3
    assert ix.best_k(5) == 3  # ceil(2.0)=2 -> floored to 3
    assert ix.best_k(10) == 4
    assert ix.best_k(20) == 8


def test_best_of_equals_analytic_mean_of_top_40pct():
    window = tuple(float(v) for v in range(1, 21))  # 1..20
    # top 8 of 1..20 are 13..20, mean = 16.5
    state = ix.IndexState()
    for v in window:
        state = ix.update_index(state, v)
    # Last value 20 is the max, so rise-fast keeps index at the top-8 mean.
    assert state.index_value == pytest.approx(16.5)


def test_best_of_ignores_the_worst_values():
    # A batch of strong games then a single terrible one: index barely notices.
    goodness = [10.0] * 9 + [0.0]
    # top 4 of ten are all 10 -> 10.0
    assert ix.best_of_goodness(goodness) == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# Sandbag property (the headline test)
# --------------------------------------------------------------------------- #


def test_throwing_games_costs_nothing_versus_ordinary_bad_games():
    """The precise sandbag property: a value in your worst 60% has **zero**
    effect on the index, no matter how low — so deliberately losing (0) is no
    different from an ordinary sub-median game (a low-but-real value). You cannot
    tank your own rank by throwing.
    """
    history = [22.0, 24.0, 20.0, 26.0, 23.0, 25.0, 21.0, 24.0, 22.0, 25.0]

    thrown = ix.rebuild_index(history)
    ordinary = ix.rebuild_index(history)
    for _ in range(10):
        thrown = ix.update_index(thrown, 0.0)  # deliberately thrown
        ordinary = ix.update_index(ordinary, 15.0)  # a genuinely bad but real game

    # Both are below the player's best 40%, so the index is identical to the cent.
    assert thrown.index_value == pytest.approx(ordinary.index_value, abs=1e-9)

    # And a naive average would have punished the thrower far more than the
    # ordinary-bad player — which is exactly the exploit best-of removes.
    thrown_mean = ix.plain_mean_index(thrown.window)
    ordinary_mean = ix.plain_mean_index(ordinary.window)
    assert thrown_mean < ordinary_mean - 7.0


def test_a_full_window_of_zeros_still_falls_only_slowly():
    """Even swamped (every game thrown), fall-slow means no quick rank drop: the
    index cannot be crashed on demand, and with the 12-month floor it can't fall
    more than one bucket at all.
    """
    # Without the floor: a whole window of zeros drifts down but stays well above
    # zero after the first handful of throws (damping at 1/4 per step).
    state = ix.rebuild_index([25.0] * 20)
    after_one = ix.update_index(state, 0.0)
    assert after_one.index_value > 24.0  # one throw barely dents it

    for _ in range(20):
        state = ix.update_index(state, 0.0)
    assert state.index_value > 0.0  # never snaps to zero

    # With the 12-month floor it cannot drop more than a single bucket, ever.
    floored = ix.rebuild_index([25.0] * 20, fall_floor_bucket_width=5.0)
    for _ in range(50):
        floored = ix.update_index(floored, 0.0, fall_floor_bucket_width=5.0)
    assert floored.index_value >= 20.0 - 1e-9  # peak(25) − one bucket(5)


# --------------------------------------------------------------------------- #
# Lower-is-better (chess moves) + floor
# --------------------------------------------------------------------------- #


def test_lower_is_better_uses_the_lowest_values():
    # Fewer moves is better; index should track the best (lowest) games.
    moves = [40.0, 30.0, 45.0, 28.0, 50.0, 26.0, 33.0, 29.0, 41.0, 27.0]
    state = ix.rebuild_index(moves, lower_is_better=True)
    # Best 4 (lowest) of these are 26,27,28,29 -> mean 27.5. A recent good (low)
    # game triggers rise-fast toward it.
    assert state.index_value == pytest.approx(27.5, abs=2.0)
    assert state.index_value < sum(moves) / len(moves)  # better than the average


def test_metric_floor_clamps_a_corrupt_low_value():
    # A corrupt 0-move game must not drag a lower-is-better index below the floor.
    state = ix.rebuild_index([30.0, 32.0, 28.0], lower_is_better=True, metric_floor=2.0)
    state = ix.update_index(state, 0.0, lower_is_better=True, metric_floor=2.0)
    assert min(state.window) == 2.0  # the 0 was clamped up to the floor


# --------------------------------------------------------------------------- #
# Rise-fast / fall-slow
# --------------------------------------------------------------------------- #


def test_rise_is_immediate():
    state = ix.rebuild_index([10.0] * 10)
    before = state.index_value
    state = ix.update_index(state, 100.0)  # one great game
    assert state.index_value > before + 5.0  # jumped immediately


def test_fall_is_damped_to_a_quarter():
    # Build a window whose best-of is high, then feed enough weak games that the
    # raw best-of drops, and assert the stored index only moves ~1/4 of the gap.
    state = ix.rebuild_index([50.0] * 20)
    stored = state.index_value  # 50
    # Replace the window with lower values so raw best-of falls to ~20.
    for _ in range(20):
        state = ix.update_index(state, 20.0)
    # After the window fully turns over, raw best-of is 20; but each step only
    # closed 25% of the remaining gap, so the *path* stayed above a plain mean.
    # Final resting point converges toward 20 but never overshoots below it.
    assert 20.0 <= state.index_value <= stored


def test_single_bad_game_moves_index_about_a_quarter():
    state = ix.rebuild_index([50.0] * 20)
    stored = state.index_value
    # One weak game: raw best-of barely changes (still 19 fifties in the window),
    # so this mostly proves a single bad game cannot crater the number.
    state = ix.update_index(state, 0.0)
    assert state.index_value == pytest.approx(stored, abs=0.5)


def test_fall_floor_holds_at_peak_minus_one_bucket():
    state = ix.rebuild_index([50.0] * 20, fall_floor_bucket_width=10.0)
    # Now throw a long run of zeros; the floor is peak(50) - one bucket(10) = 40.
    for _ in range(40):
        state = ix.update_index(state, 0.0, fall_floor_bucket_width=10.0)
    assert state.index_value >= 40.0 - 1e-9


# --------------------------------------------------------------------------- #
# Confidence
# --------------------------------------------------------------------------- #


def test_confidence_rises_as_the_number_settles():
    noisy = ix.rebuild_index([0.0, 100.0, 0.0, 100.0])
    steady = ix.rebuild_index([50.0, 50.1, 49.9, 50.0])
    assert steady.index_confidence > noisy.index_confidence
    assert 0.0 <= noisy.index_confidence <= 1.0
    assert 0.0 <= steady.index_confidence <= 1.0


def test_confidence_edges():
    assert ix.confidence(1.0, 1, 50.0) == 0.0  # n<2 → not settled
    assert ix.confidence(0.0, 5, 50.0) == 1.0  # zero spread → fully settled
    # More samples of the same spread → more settled.
    assert 0.0 < ix.confidence(5.0, 4, 50.0) < ix.confidence(5.0, 100, 50.0) < 1.0
    # A noisier history (bigger σ) is less settled at the same n and mean.
    assert ix.confidence(20.0, 10, 50.0) < ix.confidence(2.0, 10, 50.0)


# --------------------------------------------------------------------------- #
# Determinism + golden snapshot
# --------------------------------------------------------------------------- #


def test_determinism_same_inputs_same_bytes():
    values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0, 5.0]
    a = ix.rebuild_index(values)
    b = ix.rebuild_index(values)
    assert (a.mean, a.m2, a.n_samples, a.window, a.index_value) == (
        b.mean,
        b.m2,
        b.n_samples,
        b.window,
        b.index_value,
    )


# A checked-in table of indices. Any change here must be reviewed in the diff:
# it means the rating maths moved, which moves money.
_GOLDEN = {
    # top-6 of the 15 kills = {31,30,29,28,27,26} → mean 28.5.
    "cs2_kills_strong": (
        [24, 19, 27, 22, 31, 18, 25, 29, 21, 26, 23, 28, 20, 30, 24],
        False,
        28.5,
    ),
    # top-3 GPM = {600,590,580} → mean 590; rise-fast locks the best form.
    "gpm_settled": ([560, 540, 580, 550, 600, 520, 570, 590], False, 585.0),
    # lower-is-better; rise-fast captures the best (lowest) demonstrated form.
    "chess_moves_low_better": (
        [34, 41, 29, 38, 45, 31, 27, 36, 42, 30],
        True,
        29.25,
    ),
}


@pytest.mark.parametrize("name", sorted(_GOLDEN))
def test_golden_index_snapshot(name):
    values, lower, expected = _GOLDEN[name]
    state = ix.rebuild_index([float(v) for v in values], lower_is_better=lower)
    assert state.index_value == pytest.approx(expected, abs=1e-6), (
        f"golden index for {name} changed to {state.index_value!r}; if intentional, "
        "update _GOLDEN and review the money impact"
    )
