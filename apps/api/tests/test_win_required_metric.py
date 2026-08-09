"""`chess_moves` must only ever count a game you won.

Without the win requirement the metric is exploitable in the cheapest possible
way. The bar reads "at or under N moves" and a resignation on move one scores 1,
so instantly resigning clears **every** tier of **every** pool. It costs
nothing, takes a second, needs no skill, and always works. That is not a
loophole at the edges, it is a strictly dominant strategy.

Two halves make it safe, and they have to agree:

- the adapter emits no value for a game you did not win, so a loss cannot
  produce a score and cannot drag your baseline either;
- grading reads a missing value on a match you *did* play as a **miss**, not as
  "unverifiable". Refunding there would hand a loss the same outcome as never
  playing, which is a free option: enter, lose, get your stake back.
"""

from __future__ import annotations

import pytest

from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter
from moneymatch_api.constants import requires_win

pytestmark = pytest.mark.nodb


def _game(**over):
    """A finished Lichess game record, as the export endpoint returns it."""
    game = {
        "id": "abc123",
        "rated": True,
        "speed": "bullet",
        "createdAt": 1_700_000_000_000,
        "status": "mate",
        "winner": "white",
        "moves": " ".join(["e4"] * 17),  # 17 plies -> 9 full moves
        "players": {
            "white": {"user": {"id": "me"}, "rating": 1100},
            "black": {"user": {"id": "you"}, "rating": 1100},
        },
    }
    game.update(over)
    return game


def _norm(**over):
    """Normalize as the poller does. `None` means the record was not usable."""
    norm = ChessLichessAdapter()._normalize(_game(**over), "me")
    assert norm is not None, "fixture should be a finished standard game"
    return norm


def test_the_metric_is_registered_as_win_only():
    assert requires_win("chess_moves") is True
    assert requires_win("cs2_kd_ratio") is False


def test_a_win_still_scores_its_move_count():
    norm = _norm()
    assert norm.won is True
    assert norm.metrics["chess_moves"] == 9.0


def test_the_instant_resign_exploit_scores_nothing():
    """The whole reason this file exists.

    Two plies then resign: one full move, which would clear any bar ever
    quoted. It must produce no value at all.
    """
    exploit = _norm(status="resign", winner="black", moves="e4 e5")
    assert exploit.won is False
    assert exploit.moves == 1  # the game really was that short
    assert "chess_moves" not in exploit.metrics


@pytest.mark.parametrize(
    ("status", "winner"),
    [("resign", "black"), ("mate", "black"), ("outoftime", "black")],
)
def test_no_loss_produces_a_value_however_it_ended(status, winner):
    assert "chess_moves" not in _norm(status=status, winner=winner).metrics


def test_a_draw_produces_no_value_either():
    """A draw is nobody's win, and the prior is fitted on decisive games."""
    drawn = _norm(status="draw", winner=None)
    assert drawn.won is False
    assert "chess_moves" not in drawn.metrics


def test_an_unfinished_game_never_reaches_grading_at_all():
    """A game still in progress is dropped by the normalizer, not scored."""
    assert ChessLichessAdapter()._normalize(_game(status="started"), "me") is None


def test_an_aborted_game_with_no_winner_scores_nothing():
    """`won is None` must not be read as a win: it is simply not a victory."""
    unknown = _norm(status="timeout", winner=None)
    assert unknown.won is not True
    assert "chess_moves" not in unknown.metrics


# --------------------------------------------------------------------------- #
# The grading half of the rule.
# --------------------------------------------------------------------------- #


def _outcome(metric: str, value: float | None, played: bool) -> str:
    """Mirror `grade_pool`'s decision for one entrant."""
    if not played:
        return "refund"  # nothing to look at, so nothing can be claimed
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
    """Only win-required metrics turn a missing value into a loss."""
    assert _outcome("cs2_kd_ratio", None, played=True) == "refund"
