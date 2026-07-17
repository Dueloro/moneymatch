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


def test_flooring_remainder_goes_to_rake():
    # A pot that doesn't divide cleanly: remainder cents land in the rake.
    split = money_math.split_weighted(1000, (50, 30, 20), 1000)
    assert sum(split.payouts_cents) + split.rake_cents == 1000
    # net = 900; 450/270/180 = 900 exactly here, so remainder 0.
    assert split.payouts_cents == (450, 270, 180)


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
