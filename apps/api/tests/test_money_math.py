"""Pure integer-cent split math: exact reconciliation, remainder → rake."""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services.money_math import (
    DEFAULT_RAKE_BPS,
    h2h_multiplier_bps,
    rake_for,
    split_pot,
)


def test_h2h_even_pot_ten_percent_is_1_80x():
    # Two $10 stakes → $20 pot, 10% rake, one winner takes $18.
    split = split_pot(2000, num_winners=1, rake_bps=1000)
    assert split.rake_cents == 200
    assert split.payouts_cents == (1800,)
    assert h2h_multiplier_bps(1000) == 18000  # ×1.80


def test_remainder_cents_land_in_rake():
    # $9.99 pot (3 × $3.33), 10% rake = 99; distributable 900 split 4 ways = 225
    # each with remainder 0 — pick winners that force a remainder instead.
    split = split_pot(999, num_winners=7, rake_bps=1000)
    # distributable 900 // 7 = 128 each (896), remainder 4 → rake 99 + 4 = 103.
    assert split.payouts_cents == (128,) * 7
    assert split.rake_cents == 103
    assert sum(split.payouts_cents) + split.rake_cents == 999


def test_zero_winners_is_all_rake():
    split = split_pot(500, num_winners=0)
    assert split.rake_cents == 500
    assert split.payouts_cents == ()


def test_rake_for_floors():
    assert rake_for(999, 1000) == 99  # 99.9 floored
    assert rake_for(2000, 1000) == 200
    assert rake_for(0, 1000) == 0


def test_rake_for_rejects_bad_input():
    with pytest.raises(ValueError):
        rake_for(-1, 1000)
    with pytest.raises(ValueError):
        rake_for(100, 20000)


@pytest.mark.parametrize("seed", range(200))
def test_split_always_reconciles(seed):
    rng = random.Random(seed)
    pot = rng.randint(0, 5_000_00)
    winners = rng.randint(1, 12)
    rake_bps = rng.choice([0, 500, 1000, 1500, DEFAULT_RAKE_BPS])
    split = split_pot(pot, num_winners=winners, rake_bps=rake_bps)
    # Exact reconciliation and non-negativity (also asserted in __post_init__).
    assert sum(split.payouts_cents) + split.rake_cents == pot
    assert split.rake_cents >= 0
    assert all(p >= 0 for p in split.payouts_cents)
    # Winners split evenly; any unevenness is absorbed by rake.
    assert len(set(split.payouts_cents)) <= 1
