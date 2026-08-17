"""Property-based money invariants (Phase 0.3). **Never delete this file.**

`Split.__post_init__` asserts `sum(payouts) + rake == pot`. That assertion is
the load-bearing rule of the whole money layer, and the example-based tests in
`test_money_math.py` only exercise the cases somebody thought of.

This file exercises the cases nobody thought of: arbitrary pots, rake rates,
winner counts and weight vectors, including the adversarial corners (pot smaller
than the winner count, zero rake, total rake, ties in a weighted split).

The invariants asserted here may not be weakened, relaxed, or made conditional.
If a change appears to require it, the change is wrong.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from moneymatch_api.services import money_math
from moneymatch_api.services.money_math import BPS_DENOMINATOR, Split

pytestmark = pytest.mark.nodb

# $0 to $1,000,000 in cents. Wide enough to catch overflow-ish arithmetic and
# integer-division drift without making the suite slow.
pots = st.integers(min_value=0, max_value=100_000_000)
rakes = st.integers(min_value=0, max_value=BPS_DENOMINATOR)
winners = st.integers(min_value=1, max_value=64)
weight_vectors = st.lists(
    st.integers(min_value=0, max_value=1000), min_size=1, max_size=16
)


def _assert_split_is_sound(split: Split, pot: int) -> None:
    """Every invariant a `Split` must satisfy, in one place."""
    # The rule.
    assert sum(split.payouts_cents) + split.rake_cents == pot
    assert split.pot_cents == pot
    # Integer cents only — a float here means money was computed in floating
    # point somewhere upstream.
    assert isinstance(split.rake_cents, int)
    assert all(isinstance(p, int) for p in split.payouts_cents)
    assert not isinstance(split.rake_cents, bool)
    # Money is never negative and never minted.
    assert split.rake_cents >= 0
    assert all(p >= 0 for p in split.payouts_cents)
    assert sum(split.payouts_cents) <= pot


@given(pot=pots, rake_bps=rakes, n=winners)
@settings(max_examples=400)
def test_split_pot_always_reconciles(pot: int, rake_bps: int, n: int):
    _assert_split_is_sound(money_math.split_pot(pot, n, rake_bps), pot)


@given(pot=pots, rake_bps=rakes, n=winners)
@settings(max_examples=200)
def test_split_pot_pays_every_winner_equally(pot: int, rake_bps: int, n: int):
    split = money_math.split_pot(pot, n, rake_bps)
    assert len(split.payouts_cents) == n
    assert len(set(split.payouts_cents)) <= 1, "equal split must be exactly equal"


@given(pot=pots, rake_bps=rakes, weights=weight_vectors)
@settings(max_examples=400)
def test_split_weighted_always_reconciles(
    pot: int, rake_bps: int, weights: list[int]
):
    split = money_math.split_weighted(pot, tuple(weights), rake_bps)
    _assert_split_is_sound(split, pot)


@given(pot=pots, rake_bps=rakes, weights=weight_vectors)
@settings(max_examples=200)
def test_split_weighted_respects_weight_ordering(
    pot: int, rake_bps: int, weights: list[int]
):
    """A strictly larger weight can never receive strictly less."""
    assume(sum(weights) > 0)
    split = money_math.split_weighted(pot, tuple(weights), rake_bps)
    for i, wi in enumerate(weights):
        for j, wj in enumerate(weights):
            if wi > wj:
                assert split.payouts_cents[i] >= split.payouts_cents[j]


@given(pot=pots, rake_bps=rakes)
@settings(max_examples=200)
def test_rake_never_exceeds_its_nominal_rate(pot: int, rake_bps: int):
    """`rake_for` floors, so it is always ≤ the true percentage of the pot."""
    rake = money_math.rake_for(pot, rake_bps)
    assert isinstance(rake, int)
    assert 0 <= rake <= pot
    assert rake * BPS_DENOMINATOR <= pot * rake_bps


# --------------------------------------------------------------------------- #
# Adversarial corners, named explicitly so a failure reads clearly.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("n", [1, 2, 3, 4, 7, 64])
def test_pot_smaller_than_winner_count(n: int):
    """1 cent among N winners: everyone gets zero and the cent becomes rake."""
    split = money_math.split_pot(1, n, 1000)
    _assert_split_is_sound(split, 1)
    assert sum(split.payouts_cents) + split.rake_cents == 1


def test_zero_rake_distributes_everything():
    split = money_math.split_pot(10_000, 4, 0)
    _assert_split_is_sound(split, 10_000)
    assert split.rake_cents == 0
    assert split.payouts_cents == (2_500, 2_500, 2_500, 2_500)


def test_total_rake_pays_nobody():
    split = money_math.split_pot(10_000, 4, BPS_DENOMINATOR)
    _assert_split_is_sound(split, 10_000)
    assert split.rake_cents == 10_000
    assert sum(split.payouts_cents) == 0


def test_zero_winners_makes_the_whole_pot_rake():
    """Documented behaviour: the refund path never calls this."""
    split = money_math.split_pot(10_000, 0, 1000)
    _assert_split_is_sound(split, 10_000)
    assert split.payouts_cents == ()
    assert split.rake_cents == 10_000


def test_weighted_split_with_ties_reconciles():
    split = money_math.split_weighted(10_000, (50, 50, 50), 1000)
    _assert_split_is_sound(split, 10_000)


def test_weighted_split_with_all_zero_weights():
    split = money_math.split_weighted(10_000, (0, 0, 0), 1000)
    _assert_split_is_sound(split, 10_000)
    assert split.rake_cents == 10_000


def test_zero_pot_is_sound_everywhere():
    _assert_split_is_sound(money_math.split_pot(0, 4, 1000), 0)
    _assert_split_is_sound(money_math.split_weighted(0, (50, 30, 20), 1000), 0)


def test_split_rejects_a_non_reconciling_construction():
    """The guard itself must actually fire."""
    with pytest.raises(ValueError):
        Split(pot_cents=100, rake_cents=10, payouts_cents=(80,))
    with pytest.raises(ValueError):
        Split(pot_cents=100, rake_cents=-10, payouts_cents=(110,))
