"""A demo tournament must settle, not cancel.

A pool grades each entrant against *their own* bar, so a practice opponent that
never plays is a miss and the pool settles with a winner. A tournament *ranks*
entries against each other, so a practice opponent has no score. It forfeits —
a participant that played nothing — and `settle_tournament` counts forfeits
toward the field and ranks them last, so a field of one real entrant and nine
forfeits settles and pays the entrant instead of cancelling.
"""

from __future__ import annotations

import uuid

import pytest

from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import telemetry_fetch, test_opponents

pytestmark = pytest.mark.asyncio

METRICS = ("chess_win_streak", "chess_wins", "chess_fastest_win", "cs2_kd_ratio")


def _bot_entry() -> TournamentEntry:
    handle = "testbot_bo"
    return TournamentEntry(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        host_account_id=f"{test_opponents.TEST_AUTH_PREFIX}{handle}",
    )


@pytest.mark.parametrize("metric", METRICS)
async def test_a_practice_opponent_forfeits_without_a_fabricated_score(metric):
    """No invented score: a practice opponent grades as a played-nothing
    forfeit (values=[], score None). The adapter is never polled, so `session`
    is unused on this branch."""
    tournament = Tournament(
        game="chess.lichess", ranking_metric=metric, score_matches=3
    )
    entry = _bot_entry()
    grades = await telemetry_fetch.grade_tournament(None, tournament, [entry])
    grade = grades[entry.id]
    assert grade.values == [] and grade.score is None
    assert grade.telemetry["practice_opponent"] is True
