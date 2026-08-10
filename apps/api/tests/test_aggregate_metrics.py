"""Aggregate tournament metrics: total wins, longest streak, fastest win.

These score a whole window rather than averaging a rate over first-N matches,
and "fastest win" ranks the other way round, so both the scoring and the
ranking direction are worth pinning down. Pure functions, no DB.
"""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services import aggregate_metrics as am
from moneymatch_api.services.tournament_engine import compute_standings

# Pure maths: no database, no host calls.
pytestmark = pytest.mark.nodb


def _game(won: bool | None, moves: int, i: int = 0) -> NormGame:
    return NormGame(
        id=str(i),
        speed="blitz",
        rated=True,
        created_at_ms=i,
        moves=moves,
        won=won,
        drawn=False,
    )


# `poll_eligible_games` returns newest-first, so chronological order here is
# reversed: win, win, loss, win, win, win.
NEWEST_FIRST = [
    _game(True, 40, 6),
    _game(True, 25, 5),
    _game(True, 60, 4),
    _game(False, 30, 3),
    _game(True, 52, 2),
    _game(True, 18, 1),
]


def test_total_wins_counts_every_win_in_the_window():
    assert am.get("chess_wins").score(NEWEST_FIRST) == 5.0


def test_streak_is_the_longest_unbroken_run_not_the_total():
    # Five wins overall, but a loss splits them 3 and 2.
    assert am.get("chess_win_streak").score(NEWEST_FIRST) == 3.0


def test_a_draw_breaks_a_streak():
    games = [_game(True, 20, 3), _game(None, 20, 2), _game(True, 20, 1)]
    assert am.get("chess_win_streak").score(games) == 1.0


def test_fastest_win_takes_the_shortest_won_game():
    assert am.get("chess_fastest_win").score(NEWEST_FIRST) == 18.0


def test_fastest_win_ignores_a_short_loss():
    """The whole point of scoring wins only.

    A plain minimum over every game is won by resigning on move one, which
    would turn the contest into a race to forfeit.
    """
    games = [_game(False, 2, 1), _game(True, 44, 2)]
    assert am.get("chess_fastest_win").score(games) == 44.0


def test_no_qualifying_result_scores_none_rather_than_zero():
    # None is a forfeit. Zero would rank *first* in a fewest-moves contest.
    assert am.get("chess_fastest_win").score([_game(False, 10, 1)]) is None
    assert am.get("chess_wins").score([]) is None


def test_direction_is_registered_per_metric():
    assert am.higher_is_better("chess_wins") is True
    assert am.higher_is_better("chess_win_streak") is True
    assert am.higher_is_better("chess_fastest_win") is False
    # Rate metrics are not in the registry and default to higher-is-better.
    assert am.higher_is_better("cs2_kd_ratio") is True
    assert am.is_aggregate("cs2_kd_ratio") is False


def _entry(name: str, minute: int):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, enqueued_at=dt.datetime(2026, 1, 1, 0, minute)
    )


def test_standings_flip_for_a_fewest_wins_metric():
    a, b, c = _entry("a", 1), _entry("b", 2), _entry("c", 3)
    scores = {a.id: 20.0, b.id: 45.0, c.id: 20.0}

    highest = [(e.name, r) for e, r in compute_standings([a, b, c], scores)]
    assert highest == [("b", 1), ("a", 2), ("c", 2)]

    fewest = [
        (e.name, r)
        for e, r in compute_standings([a, b, c], scores, higher_is_better=False)
    ]
    assert fewest == [("a", 1), ("c", 1), ("b", 3)]


def test_a_forfeit_never_ranks_in_either_direction():
    a, b = _entry("a", 1), _entry("b", 2)
    scores: dict[uuid.UUID, float | None] = {a.id: 30.0, b.id: None}
    for direction in (True, False):
        ranked = compute_standings([a, b], scores, higher_is_better=direction)
        assert [e.name for e, _ in ranked] == ["a"]
