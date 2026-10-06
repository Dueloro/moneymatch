"""A demo tournament must settle, not cancel.

A tournament *ranks* entries against each other, so a practice opponent (demo
bot) has no score. It forfeits — a participant that played nothing — and
`settle_tournament` counts forfeits toward the field and ranks them last, so a
field of one real entrant and bots settles and pays the entrant instead of
cancelling. Scoring never looks a bot up: it has no host account.
"""

from __future__ import annotations

import uuid

import pytest

from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import test_opponents, tournament_scoring

pytestmark = pytest.mark.asyncio

METRICS = ("chess_points", "chess_wins", "cs2_kd_ratio", "pubg_kills")


def _bot_entry() -> TournamentEntry:
    return TournamentEntry(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        host_account_id=f"{test_opponents.TEST_AUTH_PREFIX}testbot_bo",
    )


@pytest.mark.parametrize("metric", METRICS)
async def test_a_practice_opponent_forfeits_without_a_fabricated_score(metric):
    tournament = Tournament(
        game="chess.lichess", ranking_metric=metric, score_matches=3
    )
    entry = _bot_entry()
    # `session` is never touched for a bot, so None is safe here.
    scores = await tournament_scoring.score_entries(None, tournament, [entry])
    assert scores[entry.id].score is None and scores[entry.id].counted == 0
