"""Market config: the fixed per-game list, derived multipliers, no odds."""

from __future__ import annotations

from moneymatch_api.constants import GAME_CHESS_LICHESS
from moneymatch_api.services import markets
from moneymatch_api.services.markets import KIND_WIN_H2H


def test_chess_offers_only_win_h2h():
    assert {m.key for m in markets.for_game(GAME_CHESS_LICHESS)} == {"win_h2h"}


def test_chess_win_h2h_needs_speed():
    m = markets.get(GAME_CHESS_LICHESS, "win_h2h")
    assert m is not None
    assert m.kind == KIND_WIN_H2H
    assert m.requires_speed is True


def test_multiplier_is_derived_18x_at_default_rake():
    m = markets.get(GAME_CHESS_LICHESS, "win_h2h")
    assert m.multiplier_bps == 18_000


def test_unknown_market_resolves_to_none():
    assert markets.get(GAME_CHESS_LICHESS, "kd_ratio") is None
    assert markets.get("chess.lichess", "nope") is None
    assert markets.get("other.game", "win_h2h") is None
