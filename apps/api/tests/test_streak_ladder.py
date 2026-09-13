"""Phase 4 test gate — the win-streak matchmaking ladder (pure, `nodb`)."""

from __future__ import annotations

import pytest

from moneymatch_api.services import streak_ladder as sl

pytestmark = pytest.mark.nodb


# --------------------------------------------------------------------------- #
# Streak transitions: win climbs, loss resets, draw holds
# --------------------------------------------------------------------------- #


def test_win_increments_loss_resets_draw_holds():
    assert sl.streak_after(0, True) == 1
    assert sl.streak_after(3, True) == 4
    assert sl.streak_after(5, False) == 0  # a loss resets to your own level
    assert sl.streak_after(5, None) == 5  # a draw/void neither climbs nor punishes
    assert sl.streak_after(-2, True) == 1  # never goes negative


def test_three_win_streak_climbs_monotonically_then_a_loss_resets():
    streak = 0
    targets = []
    for _ in range(3):
        streak = sl.streak_after(streak, True)
        targets.append(sl.matchmaking_target(20.0, streak, rung_size=2.0))
    # Win → higher, win again → higher still (monotonic climb).
    assert targets[0] < targets[1] < targets[2]
    # A loss resets to your own level.
    streak = sl.streak_after(streak, False)
    assert sl.matchmaking_target(20.0, streak, rung_size=2.0) == 20.0


# --------------------------------------------------------------------------- #
# Fish protection: never above your own level unless you climbed there
# --------------------------------------------------------------------------- #


def test_at_zero_streak_target_is_your_own_level():
    assert sl.matchmaking_target(30.0, 0, rung_size=5.0) == 30.0
    assert sl.climb_rungs(0) == 0


def test_offset_is_never_negative_so_you_are_never_aimed_below_yourself():
    for streak in range(-3, 10):
        assert sl.target_offset(streak, rung_size=3.0) >= 0.0


def test_a_loss_drops_you_back_to_your_level_not_below():
    # Climb, then lose: target returns exactly to own index, never under it.
    streak = 4
    climbed = sl.matchmaking_target(50.0, streak, rung_size=4.0)
    assert climbed > 50.0
    reset = sl.matchmaking_target(50.0, sl.streak_after(streak, False), rung_size=4.0)
    assert reset == 50.0


# --------------------------------------------------------------------------- #
# Cap: the climb is bounded (a streak can't fling you arbitrarily far up)
# --------------------------------------------------------------------------- #


def test_climb_is_capped():
    assert sl.climb_rungs(100) == sl.STREAK_MAX_RUNGS
    capped = sl.matchmaking_target(0.0, 100, rung_size=1.0)
    assert capped == sl.STREAK_MAX_RUNGS * 1.0


# --------------------------------------------------------------------------- #
# Direction: lower-is-better aims the target the other way
# --------------------------------------------------------------------------- #


def test_lower_is_better_targets_a_lower_value():
    # Chess moves: a stronger opponent wins in *fewer* moves, so climbing aims the
    # target down, not up.
    higher = sl.matchmaking_target(30.0, 3, rung_size=2.0, lower_is_better=False)
    lower = sl.matchmaking_target(30.0, 3, rung_size=2.0, lower_is_better=True)
    assert higher > 30.0 > lower
    # Symmetric magnitude.
    assert (higher - 30.0) == pytest.approx(30.0 - lower)


# --------------------------------------------------------------------------- #
# Anti-smurf: a winning run climbs out of the starting band fast
# --------------------------------------------------------------------------- #


def test_a_smurf_climbs_out_of_the_bottom_bucket_within_a_few_wins():
    # 3 buckets over [0, 90]; a smurf starts placed in bucket 0.
    num_buckets = 3
    streak = 0
    bucket = sl.target_bucket(0, streak, num_buckets=num_buckets)
    assert bucket == 0
    # Two wins per bucket step (half-bucket rung) → out of bucket 0 within ~4 wins.
    climbed_buckets = []
    for _ in range(6):
        streak = sl.streak_after(streak, True)
        climbed_buckets.append(sl.target_bucket(0, streak, num_buckets=num_buckets))
    assert max(climbed_buckets) >= 1  # left the fish bucket
    assert max(climbed_buckets) <= num_buckets - 1  # never past the top band


def test_target_bucket_never_below_own_and_clamped_to_top():
    assert sl.target_bucket(1, 0, num_buckets=3) == 1  # own bucket at no streak
    assert sl.target_bucket(2, 100, num_buckets=3) == 2  # clamped to top band
    assert sl.target_bucket(0, 100, num_buckets=3) == 2  # capped climb, not beyond


# --------------------------------------------------------------------------- #
# rung sizing helper
# --------------------------------------------------------------------------- #


def test_rung_size_from_bucket_width():
    assert sl.rung_size_from_bucket_width(10.0) == 5.0  # half a bucket
    assert sl.rung_size_from_bucket_width(0.0) == 1.0  # fallback when unknown


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def test_deterministic():
    a = [sl.matchmaking_target(12.5, s, rung_size=1.3) for s in range(8)]
    b = [sl.matchmaking_target(12.5, s, rung_size=1.3) for s in range(8)]
    assert a == b
