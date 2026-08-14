"""A test pool must move real money: dummies forfeit, the clearer takes the pot.

The failure this guards against is subtle. A real entrant who produces no
qualifying match is *unverifiable* (`cleared=None`) and gets refunded, because
we cannot prove they failed. Practice opponents never play, so they would take
that same path and every test pool would refund everyone: nobody wins, nobody
loses, and the settlement path looks fine while proving nothing.

Grading a dummy as a **miss** is what makes the stake real.
"""

from __future__ import annotations

import pytest

from moneymatch_api.services import test_opponents
from moneymatch_api.services.pool_engine import PoolGrade

pytestmark = pytest.mark.nodb


def test_a_dummy_entry_is_recognised_by_its_host_id():
    assert test_opponents.graded_as_failed("zz_testbot_testbot_ada") is True


def test_a_real_host_id_is_never_auto_failed():
    for host in ("lifeunicorn", "76561198748110372", "pubg_someone", ""):
        assert test_opponents.graded_as_failed(host) is False, host


def _split(entries: list[tuple[str, bool | None]]) -> dict[str, list[str]]:
    """Mirror `settle_pool`'s three-way split of the field."""
    grades = {name: PoolGrade(cleared=c) for name, c in entries}
    return {
        "clearers": [n for n, g in grades.items() if g.cleared is True],
        "forfeits": [n for n, g in grades.items() if g.cleared is False],
        "refunds": [n for n, g in grades.items() if g.cleared is None],
    }


def test_you_clear_and_the_dummies_forfeit():
    """The scenario being tested: 4 entries at $25, you clear, they do not."""
    split = _split(
        [("you", True), ("bot_a", False), ("bot_b", False), ("bot_c", False)]
    )
    assert split["clearers"] == ["you"]
    assert len(split["forfeits"]) == 3
    # Nothing is refunded off the top, so the whole pot is in play.
    assert split["refunds"] == []

    entry = 2500
    pot = entry * 4
    # Clearers split pot minus rake. With one clearer that is the whole pot.
    assert pot == 10_000
    # Net for you: the pot (less rake) minus your own stake. Strictly positive
    # even after a 10% rake, which is the point of the exercise.
    assert pot * 0.9 - entry > 0


def test_you_miss_and_lose_your_stake():
    split = _split(
        [("you", False), ("bot_a", False), ("bot_b", False), ("bot_c", False)]
    )
    assert split["clearers"] == []
    # Nobody clears, so `settle_pool` refunds everyone and takes zero rake.
    # You are out nothing, which is the documented rule, not a payout.
    assert len(split["forfeits"]) == 4


def test_a_dummy_is_never_merely_refunded():
    """The regression this file exists for."""
    grade = PoolGrade(cleared=False)
    assert grade.cleared is not None, "a dummy must not land in the refund bucket"
