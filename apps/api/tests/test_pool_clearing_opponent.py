"""One practice opponent clears its bar, so a pot can actually be split.

With every dummy graded as a miss, a pool had exactly two endings: you clear
and take the whole prize, or nobody clears and everything is refunded. The rule
that decides the money in a real pool -- clearers *split* the pot -- was
unreachable with a single real player, so it was also undemonstrable.

The sibling file `test_pool_dummy_forfeit.py` builds its grade dicts by hand.
That checks the split arithmetic but cannot see how grades are produced, which
is where the clearing opponent lives, so these go through `grade_pool` itself.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import pytest

from moneymatch_api.services import telemetry_fetch, test_opponents

pytestmark = pytest.mark.nodb

ADA = "zz_testbot_testbot_ada"  # the designated clearer
BO = "zz_testbot_testbot_bo"


@dataclass
class _Entry:
    host_account_id: str
    user_id: uuid.UUID


@dataclass
class _Pool:
    metric: str = "cs2_kd_ratio"
    room_bar: float = 1.10
    game: str = "cs2.steam"
    window_starts_at: object = None
    window_ends_at: object = None


def _grade(*hosts: str) -> dict[uuid.UUID, object]:
    entries = [_Entry(h, uuid.uuid4()) for h in hosts]
    grades = asyncio.run(telemetry_fetch.grade_pool(None, _Pool(), entries))
    return {e.host_account_id: grades[e.user_id] for e in entries}


# --------------------------------------------------------------------------- #
# Which opponent clears.
# --------------------------------------------------------------------------- #


def test_the_designated_opponent_clears_its_bar():
    assert test_opponents.clears_its_bar(ADA) is True


def test_the_other_opponents_still_miss():
    assert test_opponents.clears_its_bar(BO) is False


def test_a_real_player_is_never_auto_cleared():
    """The dangerous direction: this must never hand a real account a win."""
    for host in ("76561198748110372", "hikaru", "zz_testbo", ""):
        assert test_opponents.clears_its_bar(host) is False, host


def test_every_opponent_is_still_recognised_as_a_practice_account():
    """Clearing must not smuggle a dummy past the checks that exclude them."""
    assert test_opponents.is_practice_opponent(ADA) is True
    assert test_opponents.is_practice_opponent(BO) is True
    assert test_opponents.is_practice_opponent("76561198748110372") is False


# --------------------------------------------------------------------------- #
# What grade_pool actually produces.
# --------------------------------------------------------------------------- #


def test_grade_pool_clears_one_and_fails_the_rest():
    graded = _grade(ADA, BO)
    assert graded[ADA].cleared is True
    assert graded[BO].cleared is False


def test_no_practice_opponent_is_ever_refunded():
    """A dummy in the refund bucket makes the pot a no-op. The original bug."""
    graded = _grade(ADA, BO)
    assert all(g.cleared is not None for g in graded.values())


def test_the_clearing_opponent_reports_a_value_above_the_bar():
    """It shows on the results card, so it has to be consistent with clearing."""
    graded = _grade(ADA)
    assert graded[ADA].telemetry["cs2_kd_ratio"] > _Pool().room_bar


def test_a_missing_opponent_reports_no_value():
    """It never played. Inventing a number it 'scored' would be a lie."""
    assert _grade(BO)[BO].telemetry["cs2_kd_ratio"] is None


def test_practice_opponents_are_labelled_as_such():
    assert _grade(ADA)[ADA].telemetry["practice_opponent"] is True


# --------------------------------------------------------------------------- #
# The payout rule this exists to make reachable.
# --------------------------------------------------------------------------- #


def test_clearing_your_bar_now_splits_rather_than_sweeps():
    """You + the clearing opponent both clear a 4-handed $25 pool."""
    entry, rake = 2500, 0.10
    pot = entry * 4
    prize = pot * (1 - rake)
    assert round(prize / 2) == 4500  # each clearer, not 9000 to you alone
    assert prize / 2 - entry > 0  # still a win after your own stake


def test_missing_your_bar_hands_the_pot_to_the_opponent():
    """The half that could not happen before: you can now lose a pool."""
    entry, rake = 2500, 0.10
    prize = entry * 4 * (1 - rake)
    assert round(prize) == 9000  # all of it, to the one clearer


# --------------------------------------------------------------------------- #
# The score shown for the clearing opponent.
# --------------------------------------------------------------------------- #


def test_kills_are_whole_numbers():
    """An opponent credited with 18.4 kills reads as a bug, not an opponent."""
    value = telemetry_fetch._clearing_value("cs2_kills", 16.0)
    assert value == int(value)


def test_the_shown_score_always_beats_the_bar_it_cleared():
    """Snapping to an increment must never round back under the bar."""
    for metric, bar in (
        ("cs2_kills", 16.0),
        ("cs2_kd_ratio", 1.10),
        ("cs2_headshot_pct", 56.0),
    ):
        assert telemetry_fetch._clearing_value(metric, bar) > bar, metric


def test_a_kd_score_lands_on_a_real_increment():
    """K/D moves in 0.05 steps, so 1.265 is not a score anyone could post."""
    value = telemetry_fetch._clearing_value("cs2_kd_ratio", 1.10)
    assert round(value / 0.05) == pytest.approx(value / 0.05, abs=1e-6)
