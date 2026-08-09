"""A demo tournament must settle, not cancel.

Pools and tournaments treat a silent entrant differently, and that difference
made the demo tournament untestable.

A pool grades each entrant against *their own* bar, so a practice opponent that
never plays is graded as a miss (`graded_as_failed`) and the pool settles with
a winner. A tournament *ranks* entries against each other, and
`compute_standings` drops anyone without a score. Nine silent opponents
therefore left a field of one, which is below `TOURNAMENT_MIN_RANKED`, so
`settle_tournament` cancelled and refunded everybody. You could enter, play
well, wait out the 48 hour window, and be handed your stake back.

The fix is that a practice opponent posts a deliberately losing score, so the
field ranks and a real entrant who plays at all finishes first.
"""

from __future__ import annotations

import pytest

from moneymatch_api.constants import TOURNAMENT_MIN_RANKED
from moneymatch_api.services import aggregate_metrics, test_opponents

pytestmark = pytest.mark.nodb

CHESS_AGGREGATES = ("chess_win_streak", "chess_wins", "chess_fastest_win")


@pytest.mark.parametrize("metric", CHESS_AGGREGATES)
def test_a_practice_opponent_posts_a_score_at_all(metric):
    """Scoring `None` is what dropped them from the standings."""
    assert test_opponents.practice_score(metric) is not None


@pytest.mark.parametrize("metric", CHESS_AGGREGATES)
def test_the_practice_score_is_the_losing_end_of_the_metric(metric):
    """Worst possible in the metric's own direction, not merely low."""
    spec = aggregate_metrics.get(metric)
    score = test_opponents.practice_score(metric)
    if spec.higher_is_better:
        assert score == 0.0  # nothing achieved
    else:
        assert score > 500  # a game length no real result reaches


@pytest.mark.parametrize("metric", CHESS_AGGREGATES)
def test_any_real_result_beats_a_practice_opponent(metric):
    """The point of the exercise: play at all and you finish above them."""
    spec = aggregate_metrics.get(metric)
    bot = test_opponents.practice_score(metric)
    # A modest but genuine result: one win, a streak of one, a 30-move win.
    real = 1.0 if spec.higher_is_better else 30.0
    better = real > bot if spec.higher_is_better else real < bot
    assert better, (metric, real, bot)


def test_a_metric_with_no_aggregate_spec_still_forfeits():
    """Unknown metrics must not invent a score."""
    assert test_opponents.practice_score("cs2_kd_ratio") is None


def test_the_field_now_clears_the_ranking_floor():
    """The arithmetic that used to cancel the contest.

    One real entrant plus nine practice opponents. Before, only the real score
    counted toward `min_ranked`.
    """
    scored_before = 1
    scored_after = 1 + 9
    assert scored_before < TOURNAMENT_MIN_RANKED  # cancelled, everyone refunded
    assert scored_after >= TOURNAMENT_MIN_RANKED  # settles and pays


@pytest.mark.parametrize("metric", CHESS_AGGREGATES)
def test_a_practice_opponent_never_outranks_a_real_entrant(metric):
    """Ten bots and one real player: the real player must come first.

    Mirrors `compute_standings`, which sorts by score in the metric's direction.
    """
    spec = aggregate_metrics.get(metric)
    real = 2.0 if spec.higher_is_better else 25.0
    field = [("you", real)] + [
        (f"bot{i}", test_opponents.practice_score(metric)) for i in range(9)
    ]
    sign = 1.0 if spec.higher_is_better else -1.0
    field.sort(key=lambda row: -sign * row[1])
    assert field[0][0] == "you", field[:3]
