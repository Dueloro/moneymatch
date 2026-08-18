"""Guards against documentation that contradicts the code it describes (1.6).

A comment that disagrees with its own code is a distinct category of defect from
a plain bug: it actively misleads whoever reads the file to check, which is
exactly what happened with the geo-fence (`# fail closed` above `return set()`)
and with the difficulty constants (a docstring quoting `k = {0.5, 1.0, 1.75}`
while the code used `{0.385, 0.842, 1.282}`).

Fixing the text once is not enough — the text drifted because nothing stopped
it. These tests are what stops it.
"""

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


def test_docstring_does_not_restate_the_difficulty_constants():
    """The k values must live in exactly one place.

    Restating them in prose is how they came to disagree. The fix is not to keep
    them in sync — it is to refuse to have a second copy at all.
    """
    doc = fairness.__doc__ or ""
    # The stale trio, in the forms it was written in.
    for stale in ("0.5,", "1.0,", "1.75", "31/16/4"):
        assert stale not in doc.replace("{0.385, 0.842, 1.282}", ""), (
            f"fairness docstring appears to restate difficulty constants ({stale!r}). "
            "Point at constants.POOL_DIFFICULTY_K instead of copying the values."
        )
    assert "POOL_DIFFICULTY_K" in doc, (
        "the docstring should name the constant it defers to"
    )


def test_difficulty_constants_are_the_documented_three():
    """A sanity anchor: the tiers themselves have not silently changed."""
    assert set(POOL_DIFFICULTY_K) == {"easy", "medium", "hard"}
    assert POOL_DIFFICULTY_K["easy"] < POOL_DIFFICULTY_K["medium"]
    assert POOL_DIFFICULTY_K["medium"] < POOL_DIFFICULTY_K["hard"]
    # Implied clear rates, which are what the card actually promises.
    for difficulty, expected in (("easy", 0.35), ("medium", 0.20), ("hard", 0.10)):
        actual = fairness.p_target_for_k(POOL_DIFFICULTY_K[difficulty])
        assert actual == pytest.approx(expected, abs=0.005), (
            f"{difficulty} tier now implies {actual:.1%}, not {expected:.0%}. If "
            "deliberate, update the cards and the golden file too."
        )


#: Increments kept for metrics that are not offered as pool/tournament markets.
#: Each needs a reason, and the reason has to survive being read out loud.
#:
#: `chess_accuracy` — Lichess only reports accuracy for games a player requested
#: analysis on, so it has no reliable per-match source and is not offered. The
#: increment is retained because the demo fixtures seed a model for it
#: (`routers/demo.py::_DEMO_METRIC_FIXTURE`). Documented in constants.py.
DOCUMENTED_ORPHAN_INCREMENTS = {"chess_accuracy"}


def test_every_bar_increment_belongs_to_a_live_market():
    """An increment for a market nobody can trade is a trap for the next reader.

    `cs2_adr` sat here after migration 0024 retired the adapter that produced it.
    Anything genuinely retained on purpose goes in the exemption set above, with
    its reason — so the exception is visible rather than implied by silence.
    """
    live = {m for metrics in POOL_METRICS.values() for m in metrics}
    live |= {m for metrics in TOURNAMENT_METRICS.values() for m in metrics}
    orphans = set(METRIC_BAR_INCREMENT) - live - DOCUMENTED_ORPHAN_INCREMENTS
    assert not orphans, (
        f"METRIC_BAR_INCREMENT has entries for markets that are not registered: "
        f"{sorted(orphans)}. Remove them, register the market, or add them to "
        "DOCUMENTED_ORPHAN_INCREMENTS with a reason."
    )


def test_documented_orphans_are_still_orphans():
    """If an exempted metric becomes live, the exemption must be removed."""
    live = {m for metrics in POOL_METRICS.values() for m in metrics}
    live |= {m for metrics in TOURNAMENT_METRICS.values() for m in metrics}
    stale = DOCUMENTED_ORPHAN_INCREMENTS & live
    assert not stale, (
        f"{sorted(stale)} is now a live market — drop it from "
        "DOCUMENTED_ORPHAN_INCREMENTS so the guard covers it again."
    )


def test_cs2_adr_is_gone():
    """Named explicitly, because it is the one that actually rotted."""
    assert "cs2_adr" not in METRIC_BAR_INCREMENT


def test_every_live_market_has_an_increment():
    """The other direction: a market with no increment falls back to 0.01.

    For a whole-number metric that silently quotes bars at a resolution the game
    cannot express.
    """
    live = {m for metrics in POOL_METRICS.values() for m in metrics}
    missing = live - set(METRIC_BAR_INCREMENT)
    assert not missing, f"pool markets with no declared increment: {sorted(missing)}"


def test_skill_prior_docstring_admits_its_scope():
    """It described a general mechanism; it drives exactly one metric."""
    doc = skill_prior.__doc__ or ""
    assert "chess_moves" in doc
    assert "no-op" in doc or "untouched" in doc, (
        "the docstring must say that shrink() is inert for metrics with no prior "
        "— otherwise it reads as though every game is shrunk toward a rating"
    )
    # And the claim must still be true.
    assert skill_prior.prior_for("cs2_kd_ratio", 1500) is None
    assert skill_prior.prior_for("chess_moves", 1500) is not None


def test_shrink_really_is_a_no_op_without_a_prior():
    """The behaviour the docstring now describes, asserted rather than trusted."""
    assert skill_prior.shrink(1.23, 0.45, 30, None) == (1.23, 0.45)


def test_fairness_source_has_no_stale_difficulty_comments():
    """`test_fairness.py` labelled 0.5/1.0/1.75 as easy/medium/hard in comments.

    Those tests pass `k` explicitly so they were never *wrong*, but the comments
    reinforced the same false mental model the docstring did.
    """
    source = inspect.getsource(fairness)
    for stale in ("Easy (k=0.5)", "Medium (k=1.0)", "Hard (k=1.75)"):
        assert stale not in source
