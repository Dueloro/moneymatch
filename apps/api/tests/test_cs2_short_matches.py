"""A surrendered game cannot settle a wager, whichever door it came through.

The paste path rejects a short match with an explanation. That check guards only
the door it is nailed to: a code collected by the share-code chain never passes
it, and neither would any ingest path added later. So the floor is enforced
where matches *become gradeable* instead — the adapter every engine reads
through — and again where baselines are computed, because a three-round abandon
is also the cheapest way to tank the bar you are quoted next.
"""

from __future__ import annotations

import pytest

from moneymatch_api.constants import (
    CS2_MIN_ROUNDS_STANDARD,
    CS2_MIN_ROUNDS_WINGMAN,
    cs2_min_rounds,
)

pytestmark = pytest.mark.nodb


def test_a_full_competitive_match_qualifies():
    assert cs2_min_rounds(10) == CS2_MIN_ROUNDS_STANDARD
    assert 16 >= cs2_min_rounds(10)


def test_a_wingman_match_has_its_own_floor():
    """Wingman is 2v2 and shorter; judging it by the 5v5 floor rejects every one."""
    assert cs2_min_rounds(4) == CS2_MIN_ROUNDS_WINGMAN
    assert cs2_min_rounds(4) < cs2_min_rounds(10)


@pytest.mark.parametrize(
    "players,rounds,gradeable",
    [
        (10, 16, True),  # a real competitive match
        (10, 15, False),  # one round short: a surrender
        (10, 3, False),  # abandoned early
        (4, 9, True),  # a real Wingman match
        (4, 8, False),  # a surrendered Wingman
    ],
)
def test_the_floor_decides_what_can_be_graded(players, rounds, gradeable):
    assert (rounds >= cs2_min_rounds(players)) is gradeable


def test_the_adapter_is_the_place_it_is_enforced():
    """Structural, not a per-caller reminder: every engine reads through here."""
    import inspect

    from moneymatch_api.adapters.cs2_steam import CS2SteamAdapter

    source = inspect.getsource(CS2SteamAdapter.poll_eligible_games)
    assert "cs2_min_rounds" in source


def test_baselines_ignore_short_matches_too():
    """Otherwise abandoning games is a way to lower the bar you are offered."""
    import inspect

    from moneymatch_api.services import cs2_baseline

    assert "cs2_min_rounds" in inspect.getsource(cs2_baseline._samples)
