"""Phase 5 test gate — best-of-N-in-window tournament scoring (pure, `nodb`)."""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services import tournament_scoring as ts

pytestmark = pytest.mark.nodb

WIN_END = 1_000_000


def _g(value, ended):
    return ts.WindowGame(value=value, ended_at_ms=ended)


# --------------------------------------------------------------------------- #
# Window cutoff: a game finishing after the window does not count
# --------------------------------------------------------------------------- #


def test_game_after_cutoff_is_excluded():
    games = [_g(10, WIN_END - 100), _g(99, WIN_END + 1)]  # the 99 crosses the cutoff
    score = ts.score_player("p", games, WIN_END, aggregation=ts.AGG_MAX)
    assert score.score == 10  # the in-progress-at-cutoff 99 is ignored


def test_no_in_window_game_means_no_score():
    games = [_g(50, WIN_END + 5)]
    assert ts.score_player("p", games, WIN_END) is None


# --------------------------------------------------------------------------- #
# Aggregation knob
# --------------------------------------------------------------------------- #


def test_max_aggregation_takes_the_best_game():
    games = [_g(10, 1), _g(25, 2), _g(18, 3)]
    s = ts.score_player("p", games, WIN_END, aggregation=ts.AGG_MAX)
    assert s.score == 25 and s.games_used == 3


def test_average_aggregation():
    games = [_g(10, 1), _g(20, 2), _g(30, 3)]
    s = ts.score_player("p", games, WIN_END, aggregation=ts.AGG_AVERAGE)
    assert s.score == pytest.approx(20.0)


def test_best_k_average_aggregation():
    games = [_g(10, 1), _g(40, 2), _g(30, 3), _g(5, 4)]
    s = ts.score_player(
        "p", games, WIN_END, aggregation=ts.AGG_BEST_K_AVERAGE, best_k=2
    )
    assert s.score == pytest.approx(35.0)  # mean of top 2 (40, 30)


def test_lower_is_better_best_is_lowest():
    games = [_g(40, 1), _g(28, 2), _g(35, 3)]  # chess moves: fewer is better
    s = ts.score_player(
        "p", games, WIN_END, aggregation=ts.AGG_MAX, lower_is_better=True
    )
    assert s.score == 28


# --------------------------------------------------------------------------- #
# Deterministic ranking + tie-break
# --------------------------------------------------------------------------- #


def test_ranking_is_by_score_then_earliest_then_fewer_games():
    a = ts.PlayerScore("a", 30.0, reached_at_ms=500, games_used=2)
    b = ts.PlayerScore("b", 30.0, reached_at_ms=300, games_used=2)  # reached it first
    c = ts.PlayerScore("c", 30.0, reached_at_ms=300, games_used=1)  # fewer games
    d = ts.PlayerScore("d", 25.0, reached_at_ms=100, games_used=1)  # lower score
    order = [s.player_id for s in ts.rank_players([a, b, c, d])]
    assert order == ["c", "b", "a", "d"]


def test_ranking_is_deterministic():
    rng = random.Random(0)
    scores = [
        ts.PlayerScore(f"p{i}", rng.choice([10.0, 20.0, 30.0]), rng.randint(0, 999), 1)
        for i in range(20)
    ]
    assert ts.rank_players(list(scores)) == ts.rank_players(list(reversed(scores)))


# --------------------------------------------------------------------------- #
# Full settlement: split 60/25/15, exact money, underfill void
# --------------------------------------------------------------------------- #


def test_top_three_split_60_25_15_reconciles():
    entries = {p: 1000 for p in ["a", "b", "c", "d", "e"]}  # pot 5000
    windows = {
        "a": [_g(50, 10)],
        "b": [_g(40, 10)],
        "c": [_g(30, 10)],
        "d": [_g(20, 10)],
        "e": [_g(10, 10)],
    }
    out = ts.settle_tournament(entries, windows, WIN_END, rake_bps=1000)
    assert not out.voided
    assert out.standings[:3] == ["a", "b", "c"]
    # Money conserved to the gem.
    assert sum(out.payouts.values()) + out.rake_cents == 5000
    # 60/25/15 of (pot - rake). rake = 10% of 5000 = 500 → distributable 4500.
    assert out.payouts["a"] == 4500 * 60 // 100
    assert out.payouts["b"] == 4500 * 25 // 100
    assert out.payouts["c"] == 4500 * 15 // 100
    assert out.payouts["d"] == 0 and out.payouts["e"] == 0


def test_underfill_voids_and_refunds_everyone():
    entries = {"a": 1000}  # only one player, min is 2
    out = ts.settle_tournament(entries, {"a": [_g(50, 10)]}, WIN_END, min_players=2)
    assert out.voided
    assert out.rake_cents == 0
    assert out.payouts == {"a": 1000}


def test_all_games_after_cutoff_voids_and_refunds():
    entries = {"a": 1000, "b": 1000}
    windows = {"a": [_g(50, WIN_END + 1)], "b": [_g(40, WIN_END + 2)]}
    out = ts.settle_tournament(entries, windows, WIN_END)
    assert out.voided
    assert out.payouts == {"a": 1000, "b": 1000}


def test_fewer_than_three_scored_truncates_the_split():
    # 4 enter, only 2 produce an in-window game → 2 places paid (60/25 truncated),
    # money still reconciles and non-scorers fund the pot.
    entries = {p: 1000 for p in ["a", "b", "c", "d"]}
    windows = {"a": [_g(50, 10)], "b": [_g(40, 10)]}  # c, d didn't play in window
    out = ts.settle_tournament(entries, windows, WIN_END, rake_bps=1000)
    assert not out.voided
    assert out.standings == ["a", "b"]
    assert out.payouts["c"] == 0 and out.payouts["d"] == 0
    assert sum(out.payouts.values()) + out.rake_cents == 4000


def test_money_invariant_across_random_tournaments():
    rng = random.Random(7)
    for _ in range(2000):
        n = rng.randint(2, 8)
        entries = {f"p{i}": rng.randint(1, 5000) for i in range(n)}
        windows = {
            pid: [
                _g(rng.uniform(0, 60), rng.randint(0, WIN_END))
                for _ in range(rng.randint(0, 3))
            ]
            for pid in entries
        }
        out = ts.settle_tournament(
            entries, windows, WIN_END, rake_bps=rng.choice([0, 500, 1000])
        )
        assert sum(out.payouts.values()) + out.rake_cents == sum(entries.values())


def test_settlement_object_rejects_a_broken_split():
    with pytest.raises(ValueError):
        ts.TournamentSettlement(
            pot_cents=1000, rake_cents=0, payouts={"a": 999}, standings=["a"],
            voided=False, reason="x",
        )
