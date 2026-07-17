"""Market config: the fixed per-game list, derived multipliers, no odds."""

from __future__ import annotations

from moneymatch_api.constants import (
    GAME_CHESS_LICHESS,
    GAME_CS2_FACEIT,
    GAME_DOTA2_OPENDOTA,
)
from moneymatch_api.services import markets
from moneymatch_api.services.markets import (
    KIND_STAT_RACE,
    KIND_WIN_H2H,
    KIND_WIN_NEXT,
)


def test_each_game_offers_its_designed_markets():
    assert {m.key for m in markets.for_game(GAME_CHESS_LICHESS)} == {"win_h2h"}
    assert {m.key for m in markets.for_game(GAME_CS2_FACEIT)} == {
        "kd_ratio",
        "adr",
        "headshot_pct",
        "win_next",
    }
    assert {m.key for m in markets.for_game(GAME_DOTA2_OPENDOTA)} == {
        "win_next",
        "kda_ratio",
        "gpm",
    }


def test_chess_is_brokered_and_needs_speed():
    m = markets.get(GAME_CHESS_LICHESS, "win_h2h")
    assert m is not None
    assert m.kind == KIND_WIN_H2H
    assert m.brokered is True
    assert m.requires_speed is True


def test_win_next_is_coordinated_not_brokered():
    m = markets.get(GAME_CS2_FACEIT, "win_next")
    assert m is not None and m.kind == KIND_WIN_NEXT
    assert m.brokered is False
    assert m.metric is None


def test_stat_races_carry_a_metric_models_key():
    m = markets.get(GAME_CS2_FACEIT, "kd_ratio")
    assert m is not None and m.kind == KIND_STAT_RACE
    assert m.metric == "cs2_kd_ratio"
    assert markets.get(GAME_DOTA2_OPENDOTA, "gpm").metric == "dota2_gpm"


def test_multiplier_is_derived_18x_at_default_rake():
    # 2·(1 − 0.10) = ×1.80 → 18000 bps (02-design-system §4). Derived, not set.
    m = markets.get(GAME_CS2_FACEIT, "kd_ratio")
    assert m.multiplier_bps == 18_000


def test_unknown_market_resolves_to_none():
    assert markets.get(GAME_CHESS_LICHESS, "kd_ratio") is None
    assert markets.get("chess.lichess", "nope") is None
