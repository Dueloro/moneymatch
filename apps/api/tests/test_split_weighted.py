"""Weighted pot split (tournaments): the settlement invariant on integer cents."""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services import money_math


def test_50_30_20_split_exact():
    # $40 pot, 10% rake → $4 rake, $36 net split 50/30/20 = 18/10.80/7.20.
    split = money_math.split_weighted(4000, (50, 30, 20), 1000)
    assert split.rake_cents == 400
    assert split.payouts_cents == (1800, 1080, 720)
    assert sum(split.payouts_cents) + split.rake_cents == 4000


def test_renormalizes_when_fewer_places_filled():
    # Only two ranked → pass weights[:2]; net 3600 split 50/30 → 2250/1350.
    split = money_math.split_weighted(4000, (50, 30), 1000)
    assert split.payouts_cents == (2250, 1350)
    assert sum(split.payouts_cents) + split.rake_cents == 4000


def test_flooring_remainder_goes_to_first_place():
    # 1001 at 10%: rake 100, 901 split 50/30/20 → 450/270/180 + 1 leftover.
    split = money_math.split_weighted(1001, (50, 30, 20), 1000)
    assert sum(split.payouts_cents) + split.rake_cents == 1001
    assert split.rake_cents == 100
    assert split.payouts_cents == (451, 270, 180)


def test_no_weights_makes_whole_pot_rake():
    split = money_math.split_weighted(1000, (), 1000)
    assert split.payouts_cents == ()
    assert split.rake_cents == 1000


@pytest.mark.parametrize("seed", range(50))
def test_invariant_holds_under_random_weighted_splits(seed):
    rng = random.Random(seed)
    pot = rng.randint(1, 500_000)
    places = rng.randint(1, 5)
    weights = tuple(rng.randint(1, 100) for _ in range(places))
    rake_bps = rng.choice([500, 1000, 1500])
    split = money_math.split_weighted(pot, weights, rake_bps)
    # sum(payouts) + rake == pot, exactly, every time; rake never negative.
    assert sum(split.payouts_cents) + split.rake_cents == pot
    assert split.rake_cents >= 0
    assert all(p >= 0 for p in split.payouts_cents)


# The spec's payout examples: 10 players × 100, 10% rake, split 60/25/15.
@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        ((60, 25, 15), (540, 225, 135)),
        # Only two scorers: the unfilled 3rd place rolls up to the winners.
        # 900 × 60/85 = 635.29…, × 25/85 = 264.70… → the leftover unit goes to
        # first place, not the house.
        ((60, 25), (636, 264)),
    ],
)
def test_spec_payout_examples(weights, expected):
    split = money_math.split_weighted(1000, weights, 1000)
    assert split.payouts_cents == expected
    assert split.rake_cents == 100  # exactly floor(pot × 10%), never more


def test_leftover_never_goes_to_the_house():
    split = money_math.split_weighted(1001, (60, 25, 15), 1000)
    assert split.rake_cents == 100  # floor(1001 × 10%)
    assert sum(split.payouts_cents) == 901
