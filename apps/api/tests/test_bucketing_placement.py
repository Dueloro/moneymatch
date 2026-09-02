"""Phase 4 test gate — placement systems & the smurf-safe stake ladder.

Pure logic, no DB (`nodb`).
"""

from __future__ import annotations

import pytest

from moneymatch_api.constants import ENTRY_PRESETS_CENTS, METRIC_PROVISIONAL_MIN_N
from moneymatch_api.services.bucketing import index as ix
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import placement as pl

pytestmark = pytest.mark.nodb

CS2_KILLS = mk.get("cs2.steam", "competitive", "cs2_kills")
CHESS_BLITZ = mk.get("chess.lichess", "blitz", "chess_moves")


# --------------------------------------------------------------------------- #
# The ladder itself
# --------------------------------------------------------------------------- #


def test_ladder_rungs_open_with_confidence():
    assert pl.stake_rung(0.0) == 0
    assert pl.stake_rung(0.59) == 0
    assert pl.stake_rung(0.60) == 1
    assert pl.stake_rung(0.80) == 2
    assert pl.stake_rung(0.92) == 3
    assert pl.stake_rung(1.0) == 3


def test_caps_mirror_entry_presets_then_uncap():
    assert pl.stake_cap_cents(0.0, provisional=False) == ENTRY_PRESETS_CENTS[0]  # $5
    assert pl.stake_cap_cents(0.60, provisional=False) == ENTRY_PRESETS_CENTS[1]  # $10
    assert pl.stake_cap_cents(0.80, provisional=False) == ENTRY_PRESETS_CENTS[2]  # $25
    assert pl.stake_cap_cents(0.95, provisional=False) is None  # uncapped


def test_provisional_is_always_pinned_to_the_floor():
    # Even a (spuriously) high confidence can't lift a provisional market's cap.
    assert pl.stake_cap_cents(0.99, provisional=True) == ENTRY_PRESETS_CENTS[0]


def test_within_cap():
    assert pl.within_cap(500, 500)
    assert not pl.within_cap(501, 500)
    assert pl.within_cap(10_000, None)  # uncapped


# --------------------------------------------------------------------------- #
# System 1 (history) placement
# --------------------------------------------------------------------------- #


def test_system1_placed_non_provisionally_above_floor():
    p = pl.place_account(
        CHESS_BLITZ, n_samples=25, index_confidence=0.95, starting_bucket=2
    )
    assert p.placed_from == "history"
    assert p.provisional is False
    assert p.stake_cap_cents is None  # settled → uncapped
    assert p.starting_bucket == 2


def test_system1_below_history_floor_is_provisional():
    p = pl.place_account(
        CHESS_BLITZ, n_samples=5, index_confidence=0.99, starting_bucket=1
    )
    assert p.provisional is True
    assert p.stake_cap_cents == ENTRY_PRESETS_CENTS[0]  # floor stake


# --------------------------------------------------------------------------- #
# System 2 (no history) placement + smurf bound
# --------------------------------------------------------------------------- #


def test_system2_bets_from_match_one_but_capped():
    p = pl.place_account(
        CS2_KILLS, n_samples=1, index_confidence=0.0, starting_bucket=0
    )
    assert p.placed_from == "live"
    assert p.provisional is True
    assert p.stake_cap_cents == ENTRY_PRESETS_CENTS[0]


def test_system2_with_prior_seeds_a_bucket():
    p = pl.place_account(
        CS2_KILLS, n_samples=0, index_confidence=0.0, starting_bucket=1, has_prior=True
    )
    assert p.placed_from == "prior"
    assert p.starting_bucket == 1


def test_cap_unlocks_on_stability_not_count():
    # A still-climbing index keeps the low cap even with many games...
    climbing = pl.place_account(
        CS2_KILLS, n_samples=40, index_confidence=0.4, starting_bucket=0
    )
    assert climbing.stake_cap_cents == ENTRY_PRESETS_CENTS[0]
    # ...while a settled index unlocks the ladder at the same count.
    settled = pl.place_account(
        CS2_KILLS, n_samples=40, index_confidence=0.95, starting_bucket=2
    )
    assert settled.stake_cap_cents is None


def test_smurf_extraction_is_bounded_by_the_confidence_cap():
    """A strong player on a fresh CS2 account: while their index is still
    climbing, the cap sits at the floor, so total exposure before the index
    catches up to their true level is bounded to a few floor-stakes.
    """
    floor = ENTRY_PRESETS_CENTS[0]
    # Simulate a smurf producing strong-but-rising kills; feed the index and, at
    # each step, the cap the ladder would allow.
    state = ix.IndexState()
    total_cap_exposure = 0
    matches_until_settled = 0
    for i in range(30):
        state = ix.update_index(state, 30.0 + i * 0.1)  # consistently strong
        provisional = pl.is_provisional(state.n_samples)
        cap = pl.stake_cap_cents(state.index_confidence, provisional=provisional)
        if cap is None:
            break  # ladder fully unlocked — index has settled to their level
        total_cap_exposure += cap
        matches_until_settled += 1

    # The account does settle (the cap opens)...
    assert matches_until_settled < 30
    # ...and until it does, the *worst-case* staked exposure per opponent is a
    # handful of floor stakes, not an unbounded bankroll.
    assert total_cap_exposure <= 20 * floor


def test_genuine_improver_is_only_briefly_capped_never_blocked():
    # A real improver's cap rises as the index settles; place_account never
    # returns a "blocked" state — only a (temporary) cap.
    early = pl.place_account(
        CS2_KILLS, n_samples=3, index_confidence=0.2, starting_bucket=0
    )
    later = pl.place_account(
        CS2_KILLS, n_samples=30, index_confidence=0.95, starting_bucket=2
    )
    assert early.stake_cap_cents == ENTRY_PRESETS_CENTS[0]
    assert later.stake_cap_cents is None
    assert early.stake_cap_cents is not None  # capped, but a number, never "no"


def test_provisional_flips_at_the_documented_n():
    assert pl.is_provisional(METRIC_PROVISIONAL_MIN_N - 1) is True
    assert pl.is_provisional(METRIC_PROVISIONAL_MIN_N) is False
