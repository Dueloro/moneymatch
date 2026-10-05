"""Tournament scoring rules over stored games, including the chess anti-farming
guards. Pure: no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from moneymatch_api.services import tournament_scoring as ts

pytestmark = pytest.mark.nodb

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=3)
CHESS = "chess.lichess"
PUBG = "pubg.steam"


def g(
    minute: int,
    *,
    result="win",
    moves=30,
    mode="blitz",
    rated=True,
    eligible=True,
    opp="opp1",
    provisional=False,
    metrics=None,
    duration_min=8,
    match_id=None,
):
    started = START + timedelta(minutes=minute)
    return SimpleNamespace(
        host_match_id=match_id or f"m{minute}",
        started_at=started,
        ended_at=started + timedelta(minutes=duration_min),
        mode=mode,
        rated=rated,
        eligible=eligible,
        result=result,
        moves=moves,
        metrics=metrics or {},
        detail={"opponent_id": opp, "opponent_provisional": provisional},
    )


def chess(games, *, entered=START, n=3):
    return ts.score_games(
        games,
        game=CHESS,
        metric="chess_points",
        window_start=START,
        window_end=END,
        entered_at=entered,
        max_counted=n,
    )


def reasons(score):
    return [v.reason for v in score.games]


# --- chess points ------------------------------------------------------------ #


def test_points_are_win_one_draw_half_loss_zero():
    s = chess(
        [
            g(0, result="win", opp="a"),
            g(10, result="draw", opp="b"),
            g(20, result="loss", opp="c"),
        ]
    )
    assert s.score == 1.5 and s.counted == 3
    assert reasons(s) == [ts.COUNTED] * 3


def test_only_the_first_three_count():
    s = chess([g(i * 10, opp=f"o{i}") for i in range(5)])
    assert s.score == 3.0
    assert reasons(s)[3:] == [ts.OVER_GAME_CAP, ts.OVER_GAME_CAP]


def test_short_game_uses_a_slot_and_scores_zero():
    # An alt resigning on move 2 earns nothing and burns one of your 3 games.
    s = chess(
        [g(0, moves=2, opp="alt"), g(10, opp="b"), g(20, opp="c"), g(30, opp="d")]
    )
    assert reasons(s) == [ts.TOO_SHORT, ts.COUNTED, ts.COUNTED, ts.OVER_GAME_CAP]
    assert s.score == 2.0


def test_resigning_early_does_not_erase_a_loss():
    s = chess([g(0, moves=3, result="loss", opp="a")])
    assert reasons(s) == [ts.TOO_SHORT]
    assert s.score == 0.0 and s.counted == 1


def test_provisional_opponent_does_not_count_or_use_a_slot():
    s = chess(
        [
            g(0, provisional=True, opp="fresh_alt"),
            g(10, opp="a"),
            g(20, opp="b"),
            g(30, opp="c"),
        ]
    )
    assert reasons(s) == [
        ts.OPPONENT_PROVISIONAL,
        ts.COUNTED,
        ts.COUNTED,
        ts.COUNTED,
    ]
    assert s.score == 3.0


def test_repeat_opponent_only_counts_once():
    s = chess([g(0, opp="friend"), g(10, opp="friend"), g(20, opp="friend")])
    assert reasons(s) == [ts.COUNTED, ts.REPEAT_OPPONENT, ts.REPEAT_OPPONENT]
    assert s.score == 1.0 and s.counted == 1


def test_non_blitz_and_casual_games_do_not_count():
    s = chess([g(0, mode="bullet"), g(10, rated=False, opp="b")])
    assert reasons(s) == [ts.WRONG_MODE, ts.WRONG_MODE]
    assert s.score is None  # no counted game → cannot place


def test_timing_rules():
    entered = START + timedelta(minutes=30)
    s = chess(
        [
            g(-20, opp="a"),  # before the tournament opened
            g(10, opp="b"),  # before this player joined
            g(175, opp="c", duration_min=10),  # still running at the end
            g(40, opp="d"),  # counts
        ],
        entered=entered,
    )
    by_id = {v.host_match_id: v.reason for v in s.games}
    assert by_id["m-20"] == ts.STARTED_BEFORE_START
    assert by_id["m10"] == ts.STARTED_BEFORE_ENTRY
    assert by_id["m175"] == ts.ENDED_AFTER_CUTOFF
    assert by_id["m40"] == ts.COUNTED
    assert s.score == 1.0


def test_every_game_gets_a_reason_and_text():
    s = chess([g(0), g(-5, opp="z")])
    assert all(v.reason for v in s.games)
    assert all(v.as_dict()["reason_text"] for v in s.games)


# --- stat tournaments (PUBG) ------------------------------------------------- #


def pubg(games, *, entered=START):
    return ts.score_games(
        games,
        game=PUBG,
        metric="pubg_kills",
        window_start=START,
        window_end=END,
        entered_at=entered,
        max_counted=3,
        rated_only=False,
    )


def test_pubg_score_is_the_best_of_the_first_three():
    s = pubg(
        [
            g(0, mode="squad-fpp", metrics={"pubg_kills": 2}),
            g(30, mode="squad-fpp", metrics={"pubg_kills": 7}),
            g(60, mode="squad-fpp", metrics={"pubg_kills": 4}),
            g(90, mode="squad-fpp", metrics={"pubg_kills": 12}),  # 4th: over cap
        ]
    )
    assert s.score == 7.0 and s.counted == 3
    assert reasons(s)[-1] == ts.OVER_GAME_CAP


def test_pubg_custom_matches_do_not_count():
    s = pubg([g(0, mode="squad", eligible=False, metrics={"pubg_kills": 20})])
    assert reasons(s) == [ts.WRONG_MODE] and s.score is None


def test_pubg_ignores_chess_only_rules():
    # Short games / opponents are chess concepts; PUBG never trips them.
    s = pubg([g(0, moves=0, provisional=True, metrics={"pubg_kills": 3})])
    assert reasons(s) == [ts.COUNTED] and s.score == 3.0
