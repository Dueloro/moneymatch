"""`chess_moves` must only ever count a game you won."""

from __future__ import annotations

import pytest

from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter
from moneymatch_api.constants import requires_win

pytestmark = pytest.mark.nodb


def _game(**over):
    game = {
        "id": "abc123",
        "rated": True,
        "speed": "bullet",
        "createdAt": 1_700_000_000_000,
        "status": "mate",
        "winner": "white",
        "moves": " ".join(["e4"] * 17),
        "players": {
            "white": {"user": {"id": "me"}, "rating": 1100},
            "black": {"user": {"id": "you"}, "rating": 1100},
        },
    }
    game.update(over)
    return game


def _norm(**over):
    norm = ChessLichessAdapter()._normalize(_game(**over), "me")
    assert norm is not None, "fixture should be a finished standard game"
    return norm


def test_the_metric_is_registered_as_win_only():
    assert requires_win("chess_moves") is True
    assert requires_win("chess_accuracy") is False


def test_a_win_still_scores_its_move_count():
    norm = _norm()
    assert norm.won is True
    assert norm.metrics["chess_moves"] == 9.0


def test_the_instant_resign_exploit_scores_nothing():
    exploit = _norm(status="resign", winner="black", moves="e4 e5")
    assert exploit.won is False
    assert exploit.moves == 1
    assert "chess_moves" not in exploit.metrics


@pytest.mark.parametrize(
    ("status", "winner"),
    [("resign", "black"), ("mate", "black"), ("outoftime", "black")],
)
def test_no_loss_produces_a_value_however_it_ended(status, winner):
    assert "chess_moves" not in _norm(status=status, winner=winner).metrics


def test_a_draw_produces_no_value_either():
    drawn = _norm(status="draw", winner=None)
    assert drawn.won is False
    assert "chess_moves" not in drawn.metrics


def test_an_unfinished_game_never_reaches_grading_at_all():
    assert ChessLichessAdapter()._normalize(_game(status="started"), "me") is None


def test_an_aborted_game_with_no_winner_scores_nothing():
    unknown = _norm(status="timeout", winner=None)
    assert unknown.won is not True
    assert "chess_moves" not in unknown.metrics


def _outcome(metric: str, value: float | None, played: bool) -> str:
    if not played:
        return "refund"
    if value is None:
        return "miss" if requires_win(metric) else "refund"
    return "clear" if value <= 12 else "miss"


def test_playing_and_losing_costs_you_the_stake():
    assert _outcome("chess_moves", None, played=True) == "miss"


def test_not_playing_at_all_is_still_refunded():
    """Unverifiable is not the same as failed, and must stay a refund."""
    assert _outcome("chess_moves", None, played=False) == "refund"


def test_a_fast_win_clears_and_a_slow_win_does_not():
    assert _outcome("chess_moves", 9.0, played=True) == "clear"
    assert _outcome("chess_moves", 30.0, played=True) == "miss"


def test_an_unmeasurable_metric_is_untouched_by_the_rule():
    assert _outcome("chess_accuracy", None, played=True) == "refund"
