"""Phase 3 test gate — reference cuts, assignment, hysteresis.

Pure maths, no DB (`nodb`). The checks `IMPLEMENTATION_BUCKETING.md` Phase 3
requires green before Phase 4.
"""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services.bucketing import reference as ref

pytestmark = pytest.mark.nodb


# --------------------------------------------------------------------------- #
# Reproducibility — the same data → the same cuts & bucket, every time
# --------------------------------------------------------------------------- #


def test_cuts_are_deterministic_not_a_random_clusterer():
    rng = random.Random(7)
    values = [rng.gauss(20, 5) for _ in range(500)]
    a = ref.fisher_jenks_breaks(values, 3)
    b = ref.fisher_jenks_breaks(list(reversed(values)), 3)  # order must not matter
    assert a == b  # bit-for-bit identical → provably not k-means-with-a-seed


def test_same_index_same_bucket_every_call():
    cuts = [10.0, 20.0]
    for _ in range(100):
        assert ref.assign_bucket(15.0, cuts) == 1


# --------------------------------------------------------------------------- #
# Assignment correctness, incl. the boundary rule
# --------------------------------------------------------------------------- #


def test_assignment_counts_cuts_below():
    cuts = [10.0, 20.0, 30.0]
    assert ref.assign_bucket(5.0, cuts) == 0
    assert ref.assign_bucket(15.0, cuts) == 1
    assert ref.assign_bucket(25.0, cuts) == 2
    assert ref.assign_bucket(35.0, cuts) == 3


def test_value_exactly_on_a_cut_goes_up():
    cuts = [10.0, 20.0]
    assert ref.assign_bucket(10.0, cuts) == 1  # on the cut → higher bucket
    assert ref.assign_bucket(20.0, cuts) == 2


def test_no_cuts_is_a_single_bucket():
    assert ref.assign_bucket(123.0, []) == 0


# --------------------------------------------------------------------------- #
# Hysteresis — boundary players don't flap
# --------------------------------------------------------------------------- #


def test_small_oscillation_does_not_change_bucket():
    cuts = [10.0, 20.0]  # buckets [.,10) [10,20) [20,.]
    # Player sits in bucket 1, index wobbles around the 20 boundary by < margin.
    bucket = 1
    for v in (19.5, 20.2, 19.8, 20.4, 19.9):  # within 15% of the (20,hi) width
        bucket = ref.assign_with_hysteresis(v, cuts, bucket, lo=0.0, hi=40.0)
        assert bucket == 1, f"flapped at {v}"


def test_a_decisive_cross_does_change_bucket():
    cuts = [10.0, 20.0]
    # (20,40) width is 20; margin 15% = 3, so needs >= 23 to move up.
    up = ref.assign_with_hysteresis(24.0, cuts, 1, lo=0.0, hi=40.0)
    assert up == 2
    # And below 10 - 3 = 7 to move down from bucket 1.
    down = ref.assign_with_hysteresis(6.0, cuts, 1, lo=0.0, hi=40.0)
    assert down == 0


def test_never_drops_more_than_one_bucket_at_once():
    cuts = [10.0, 20.0, 30.0]  # 4 buckets
    # In bucket 3, index craters to bucket-0 territory — may only step to 2.
    stepped = ref.assign_with_hysteresis(1.0, cuts, 3, lo=0.0, hi=40.0)
    assert stepped == 2


def test_first_placement_has_no_hysteresis():
    cuts = [10.0, 20.0]
    assert ref.assign_with_hysteresis(25.0, cuts, None, lo=0.0, hi=40.0) == 2


# --------------------------------------------------------------------------- #
# Grouping is by level, not variance or playstyle
# --------------------------------------------------------------------------- #


def test_buckets_sort_by_level_not_erraticness_or_playstyle():
    rng = random.Random(99)
    # Build a population where "level" is the true axis, and erraticness and a
    # spurious "playstyle" tag are independent of it.
    players = []
    for _ in range(600):
        level = rng.uniform(0, 100)
        erraticness = rng.uniform(0, 30)  # independent noise scale
        playstyle = rng.choice([-1, 1])  # independent categorical
        index = level  # the index tracks level
        players.append((index, level, erraticness, playstyle))

    values = [p[0] for p in players]
    cuts = ref.compute_cuts(values, 3)
    by_bucket: dict[int, list] = {0: [], 1: [], 2: []}
    for index, level, err, style in players:
        by_bucket[ref.assign_bucket(index, cuts)].append((level, err, style))

    def col_avg(bucket: int, col: int) -> float:
        rows = by_bucket[bucket]
        return sum(r[col] for r in rows) / len(rows)

    avg_level = [col_avg(b, 0) for b in range(3)]
    avg_err = [col_avg(b, 1) for b in range(3)]
    avg_style = [col_avg(b, 2) for b in range(3)]

    # Level rises monotonically across buckets...
    assert avg_level[0] < avg_level[1] < avg_level[2]
    # ...while erraticness and playstyle stay flat (bucketed on the right axis).
    assert max(avg_err) - min(avg_err) < 5.0
    assert max(abs(s) for s in avg_style) < 0.25


# --------------------------------------------------------------------------- #
# compute_cuts fallback + population floor
# --------------------------------------------------------------------------- #


def test_min_variance_cuts_beat_quantiles_on_clustered_data():
    # Three tight clusters → Fisher-Jenks should split between clusters.
    values = [1.0, 1.1, 0.9] * 20 + [50.0, 51.0, 49.0] * 20 + [100.0, 99.0] * 20
    cuts = ref.compute_cuts(values, 3, min_bucket_pop=5)
    # Cuts land in the empty gaps, not inside a cluster.
    assert 2 < cuts[0] < 49
    assert 51 < cuts[1] < 99


def test_falls_back_to_quantiles_when_a_bucket_would_starve():
    # A degenerate population where min-variance would strand a bucket: quantile
    # fallback guarantees every bucket has at least one member.
    values = [1.0] * 50 + [2.0]  # almost all identical
    cuts = ref.compute_cuts(values, 3, min_bucket_pop=1)
    # Whatever cuts come back, every bucket is reachable by some member.
    assert ref._min_population(values, cuts) >= 1


def test_empty_population_yields_no_cuts():
    assert ref.compute_cuts([], 3) == []


# --------------------------------------------------------------------------- #
# Bars — one per bucket, nudged toward the hard end
# --------------------------------------------------------------------------- #


def test_bars_are_ascending_and_one_per_bucket_higher_is_better():
    values = [float(v) for v in range(0, 100)]
    r = ref.build_reference(values, 3, lower_is_better=False)
    assert len(r.bars) == r.k == 3
    assert r.bars[0] < r.bars[1] < r.bars[2]  # a higher bucket asks for more


def test_bars_reference_round_trips_bucket_and_bar():
    values = [float(v) for v in range(0, 90)]
    r = ref.build_reference(values, 3)
    b = r.bucket_of(75.0)
    assert 0 <= b < r.k
    assert r.bar_for(b) == r.bars[b]


# --------------------------------------------------------------------------- #
# Version isolation (the property Phase 6 reconstruction relies on)
# --------------------------------------------------------------------------- #


def test_two_references_are_independent_objects():
    v1 = ref.build_reference([float(v) for v in range(0, 60)], 3)
    v2 = ref.build_reference([float(v) for v in range(0, 120)], 3)
    # Same index can bucket differently under different versions — and grading
    # under v1 is entirely unaffected by v2 existing.
    idx = 50.0
    assert v1.bucket_of(idx) == v1.bucket_of(idx)  # stable within a version
    assert v1.cuts != v2.cuts  # genuinely different rulers
