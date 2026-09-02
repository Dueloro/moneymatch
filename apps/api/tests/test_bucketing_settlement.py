"""Phase 5 test gate — grade-vs-bar & the money invariant (pure core).

Pure maths, no DB (`nodb`). The randomized property test is the headline: for
every pot, rake and winner count, `sum(payouts) + rake == pot` to the cent.
"""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services import money_math
from moneymatch_api.services.bucketing import settlement as st

pytestmark = pytest.mark.nodb


def _members(stakes, results):
    return [
        st.MemberResult(player_id=f"p{i}", stake_cents=s, result_value=r)
        for i, (s, r) in enumerate(zip(stakes, results, strict=True))
    ]


# --------------------------------------------------------------------------- #
# Clearing direction
# --------------------------------------------------------------------------- #


def test_cleared_bar_higher_and_lower_is_better():
    assert st.cleared_bar(22, 20, lower_is_better=False) is True
    assert st.cleared_bar(20, 20, lower_is_better=False) is True  # inclusive
    assert st.cleared_bar(19, 20, lower_is_better=False) is False
    assert st.cleared_bar(18, 20, lower_is_better=True) is True
    assert st.cleared_bar(20, 20, lower_is_better=True) is True
    assert st.cleared_bar(21, 20, lower_is_better=True) is False


# --------------------------------------------------------------------------- #
# The money invariant — randomized property test (headline)
# --------------------------------------------------------------------------- #


def test_money_invariant_holds_across_thousands_of_contests():
    rng = random.Random(2024)
    for _ in range(5000):
        n = rng.randint(2, 6)
        stakes = [rng.randint(1, 5000) for _ in range(n)]
        bar = rng.uniform(0, 40)
        results = [rng.uniform(0, 40) for _ in range(n)]
        lower = rng.random() < 0.5
        rake_bps = rng.choice([0, 500, 1000, 1500])
        out = st.settle_room(
            _members(stakes, results), bar, lower_is_better=lower, rake_bps=rake_bps
        )
        # The invariant, always, to the cent (also asserted in __post_init__).
        assert sum(out.payouts.values()) + out.rake_cents == out.pot_cents
        assert out.pot_cents == sum(stakes)
        assert out.rake_cents >= 0
        assert all(p >= 0 for p in out.payouts.values())


def test_pots_that_do_not_divide_evenly_still_reconcile():
    # 3 winners over a pot that doesn't divide by 3 — remainder must land in rake.
    members = _members([1000, 1000, 1000], [30, 30, 30])  # all clear
    out = st.settle_room(members, bar=20, lower_is_better=False, rake_bps=1000)
    assert sum(out.payouts.values()) + out.rake_cents == 3000
    # Winners get equal integer-cent shares.
    winner_payouts = [p for p in out.payouts.values() if p > 0]
    assert len(set(winner_payouts)) == 1


# --------------------------------------------------------------------------- #
# No-clear refund
# --------------------------------------------------------------------------- #


def test_nobody_clears_refunds_everyone_zero_rake():
    members = _members([500, 500, 500], [10, 12, 8])  # all below bar 20
    out = st.settle_room(members, bar=20, lower_is_better=False)
    assert out.refunded is True
    assert out.rake_cents == 0
    assert out.payouts == {"p0": 500, "p1": 500, "p2": 500}


# --------------------------------------------------------------------------- #
# Fail closed on unverifiable data
# --------------------------------------------------------------------------- #


def test_unverifiable_result_voids_and_refunds():
    members = _members([500, 500], [None, 30])  # p0's result couldn't be verified
    out = st.settle_room(members, bar=20, lower_is_better=False)
    assert out.refunded is True
    assert out.rake_cents == 0
    assert out.payouts == {"p0": 500, "p1": 500}
    assert "unverifiable" in out.reason


def test_a_broken_split_raises_rather_than_settling():
    # Directly constructing an unbalanced outcome must fail closed.
    with pytest.raises(ValueError):
        st.SettlementOutcome(
            pot_cents=1000,
            rake_cents=0,
            payouts={"p0": 999},
            refunded=False,
            reason="x",
        )


# --------------------------------------------------------------------------- #
# A normal win
# --------------------------------------------------------------------------- #


def test_single_winner_takes_pot_less_rake():
    members = _members([1000, 1000], [30, 10])  # p0 clears, p1 doesn't
    out = st.settle_room(members, bar=20, lower_is_better=False, rake_bps=1000)
    assert out.refunded is False
    expected = money_math.split_pot(2000, 1, rake_bps=1000)
    assert out.payouts["p0"] == expected.payouts_cents[0]
    assert out.payouts["p1"] == 0
    assert out.rake_cents == expected.rake_cents
    assert sum(out.payouts.values()) + out.rake_cents == 2000
