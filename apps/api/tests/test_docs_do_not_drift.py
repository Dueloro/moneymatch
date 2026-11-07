"""Guards against documentation that contradicts the code it describes."""

from __future__ import annotations

import inspect

import pytest

from moneymatch_api.constants import (
    METRIC_BAR_INCREMENT,
    POOL_DIFFICULTY_K,
    POOL_METRICS,
    TOURNAMENT_METRICS,
)
from moneymatch_api.services import fairness, skill_prior

pytestmark = pytest.mark.nodb


def test_difficulty_constants_are_the_documented_three():
    assert set(POOL_DIFFICULTY_K) == {"easy", "medium", "hard"}
    assert POOL_DIFFICULTY_K["easy"] < POOL_DIFFICULTY_K["medium"]
    assert POOL_DIFFICULTY_K["medium"] < POOL_DIFFICULTY_K["hard"]
    for difficulty, expected in (("easy", 0.35), ("medium", 0.20), ("hard", 0.10)):
        actual = fairness.p_target_for_k(POOL_DIFFICULTY_K[difficulty])
        assert actual == pytest.approx(expected, abs=0.005), (
            f"{difficulty} tier now implies {actual:.1%}, not {expected:.0%}. If "
            "deliberate, update the cards and the golden file too."
        )


DOCUMENTED_ORPHAN_INCREMENTS = {"chess_accuracy"}


def test_every_bar_increment_belongs_to_a_live_market():
    live = {m for metrics in POOL_METRICS.values() for m in metrics}
    live |= {m for metrics in TOURNAMENT_METRICS.values() for m in metrics}
    orphans = set(METRIC_BAR_INCREMENT) - live - DOCUMENTED_ORPHAN_INCREMENTS
    assert not orphans, (
        f"METRIC_BAR_INCREMENT has entries for markets that are not registered: "
        f"{sorted(orphans)}. Remove them, register the market, or add them to "
        "DOCUMENTED_ORPHAN_INCREMENTS with a reason."
    )


def test_documented_orphans_are_still_orphans():
    live = {m for metrics in POOL_METRICS.values() for m in metrics}
    live |= {m for metrics in TOURNAMENT_METRICS.values() for m in metrics}
    stale = DOCUMENTED_ORPHAN_INCREMENTS & live
    assert not stale, (
        f"{sorted(stale)} is now a live market — drop it from "
        "DOCUMENTED_ORPHAN_INCREMENTS so the guard covers it again."
    )


def test_every_live_market_has_an_increment():
    live = {m for metrics in POOL_METRICS.values() for m in metrics}
    missing = live - set(METRIC_BAR_INCREMENT)
    assert not missing, f"pool markets with no declared increment: {sorted(missing)}"


def test_skill_prior_only_covers_chess_moves():
    assert skill_prior.prior_for("chess_accuracy", 1500) is None
    assert skill_prior.prior_for("chess_moves", 1500) is not None


def test_shrink_really_is_a_no_op_without_a_prior():
    assert skill_prior.shrink(1.23, 0.45, 30, None) == (1.23, 0.45)


def test_fairness_source_has_no_stale_difficulty_comments():
    source = inspect.getsource(fairness)
    for stale in ("Easy (k=0.5)", "Medium (k=1.0)", "Hard (k=1.75)"):
        assert stale not in source
