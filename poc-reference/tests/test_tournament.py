"""Tests for the multi-entrant tournament engine (api/_lib/tournament.py).

The load-bearing property is the escrow/rake invariant — ``sum(payouts) + rake
== sum(entries)`` — which must hold on every settlement path (overview §7.1).
"""

import random

import pytest

from _lib import solo_challenge, tournament
from _lib.schemas import TelemetrySample, Tournament


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _entries_total(t: Tournament) -> float:
    return round(t.entry_fee * len(t.entrants), 2)


def _payouts_total(t: Tournament) -> float:
    return round(sum(e.payout for e in t.entrants), 2)


def _assert_invariant(t: Tournament) -> None:
    """sum(payouts) + rake == sum(entries), exactly, to the cent."""
    assert round(_payouts_total(t) + t.rake, 2) == _entries_total(t)
    assert t.rake >= 0.0


def _make(entry_fee=10.0, rake_pct=0.10, max_entrants=8, min_entrants=2,
          prize_split=None, metric="chess_accuracy_pct") -> Tournament:
    return tournament.create_tournament(
        "chess.lichess", "Test Cup", metric, entry_fee=entry_fee,
        rake_pct=rake_pct, max_entrants=max_entrants, min_entrants=min_entrants,
        prize_split=prize_split or [0.6, 0.3, 0.1],
    )


def _enter(t: Tournament, player_id: str, state="Massachusetts") -> None:
    tournament.enter_tournament(t, player_id, state)


def _tel(score: float, game="chess.lichess", metric="chess_accuracy_pct") -> TelemetrySample:
    return TelemetrySample(game=game, metrics={metric: score})


# --------------------------------------------------------------------------- #
# Entry mechanics
# --------------------------------------------------------------------------- #

def test_entry_escrows_and_updates_pool():
    t = _make(entry_fee=5.0)
    _enter(t, "alice")
    _enter(t, "bob")
    assert len(t.entrants) == 2
    assert t.pool == 10.0


def test_entry_is_idempotent_per_player():
    t = _make()
    _enter(t, "alice")
    _enter(t, "alice")
    assert len(t.entrants) == 1


def test_full_field_is_rejected():
    t = _make(max_entrants=2)
    _enter(t, "alice")
    _enter(t, "bob")
    with pytest.raises(tournament.TournamentFullError):
        _enter(t, "carol")


def test_geofence_blocks_restricted_state_before_charging():
    t = _make()
    with pytest.raises(solo_challenge.RegionBlockedError):
        _enter(t, "alice", state="Florida")
    assert t.entrants == []  # never charged


# --------------------------------------------------------------------------- #
# Settlement — happy path
# --------------------------------------------------------------------------- #

def test_top_n_split_and_ranking():
    t = _make(entry_fee=10.0, rake_pct=0.10, prize_split=[0.6, 0.3, 0.1])
    for p in ("a", "b", "c", "d"):
        _enter(t, p)
    # Distinct scores so ranking is unambiguous.
    telemetry = {
        "a": _tel(90),  # 1st
        "b": _tel(80),  # 2nd
        "c": _tel(70),  # 3rd
        "d": _tel(60),  # out of the money
    }
    tournament.settle_tournament(t, telemetry)

    assert t.status == "SETTLED"
    by_id = {e.player_id: e for e in t.entrants}
    assert (by_id["a"].rank, by_id["b"].rank, by_id["c"].rank, by_id["d"].rank) == (1, 2, 3, 4)
    assert by_id["a"].status == "PAID" and by_id["d"].status == "OUT"
    assert by_id["d"].payout == 0.0
    # Pool 40, rake 10% = 4, net 36 split 60/30/10.
    assert t.rake == 4.0
    assert by_id["a"].payout == pytest.approx(21.6, abs=0.01)
    assert by_id["b"].payout == pytest.approx(10.8, abs=0.01)
    assert by_id["c"].payout == pytest.approx(3.6, abs=0.01)
    _assert_invariant(t)


def test_lower_is_better_inverts_ranking():
    t = _make(prize_split=[1.0], metric="chess_accuracy_pct")
    t.higher_is_better = False
    for p in ("a", "b", "c"):
        _enter(t, p)
    tournament.settle_tournament(t, {"a": _tel(50), "b": _tel(90), "c": _tel(70)})
    winner = next(e for e in t.entrants if e.rank == 1)
    assert winner.player_id == "a"  # lowest score wins
    _assert_invariant(t)


# --------------------------------------------------------------------------- #
# Settlement — refund / edge paths
# --------------------------------------------------------------------------- #

def test_under_min_entrants_cancels_and_refunds():
    t = _make(entry_fee=10.0, min_entrants=3)
    _enter(t, "a")
    _enter(t, "b")
    tournament.settle_tournament(t, {"a": _tel(90), "b": _tel(80)})
    assert t.status == "CANCELED"
    assert all(e.status == "REFUNDED" and e.payout == 10.0 for e in t.entrants)
    assert t.rake == 0.0
    _assert_invariant(t)


def test_no_verifiable_results_refunds_all_no_rake():
    t = _make(entry_fee=10.0)
    for p in ("a", "b"):
        _enter(t, p)
    # Empty telemetry → nothing verifiable.
    tournament.settle_tournament(t, {})
    assert t.status == "SETTLED"
    assert all(e.status == "REFUNDED" for e in t.entrants)
    assert t.rake == 0.0
    _assert_invariant(t)


def test_unverifiable_entry_refunded_out_of_pool():
    t = _make(entry_fee=10.0, rake_pct=0.10, prize_split=[1.0])
    for p in ("a", "b", "c"):
        _enter(t, p)
    # c has no telemetry → refunded; a/b ranked, a wins.
    tournament.settle_tournament(t, {"a": _tel(90), "b": _tel(70)})
    by_id = {e.player_id: e for e in t.entrants}
    assert by_id["c"].status == "REFUNDED" and by_id["c"].payout == 10.0
    # Distributable = 30 - 10 refund = 20; rake 10% = 2; winner takes 18.
    assert t.rake == pytest.approx(2.0, abs=0.01)
    assert by_id["a"].payout == pytest.approx(18.0, abs=0.01)
    _assert_invariant(t)


def test_fewer_ranked_than_prize_places_renormalizes():
    # 3 prize places but only 2 verifiable finishers → split the whole net pool.
    t = _make(entry_fee=10.0, rake_pct=0.10, prize_split=[0.6, 0.3, 0.1], min_entrants=2)
    for p in ("a", "b"):
        _enter(t, p)
    tournament.settle_tournament(t, {"a": _tel(90), "b": _tel(80)})
    # Net = 20 - 2 rake = 18, weights 0.6/0.3 renormalized to 2/3 & 1/3.
    by_id = {e.player_id: e for e in t.entrants}
    assert by_id["a"].payout == pytest.approx(12.0, abs=0.01)
    assert by_id["b"].payout == pytest.approx(6.0, abs=0.01)
    _assert_invariant(t)


# --------------------------------------------------------------------------- #
# Invariant fuzz — many random settlements
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("seed", range(25))
def test_invariant_holds_under_random_settlement(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 9)
    t = _make(
        entry_fee=rng.choice([1.0, 5.0, 7.5, 10.0, 25.0]),
        rake_pct=rng.choice([0.05, 0.10, 0.15]),
        max_entrants=10,
        min_entrants=2,
        prize_split=rng.choice([[1.0], [0.6, 0.4], [0.6, 0.3, 0.1], [0.5, 0.3, 0.15, 0.05]]),
    )
    for i in range(n):
        _enter(t, f"p{i}")
    telemetry = {}
    for i in range(n):
        # Some entrants randomly have no telemetry (un-verifiable).
        if rng.random() < 0.2:
            continue
        telemetry[f"p{i}"] = _tel(rng.uniform(40, 99))
    tournament.settle_tournament(t, telemetry)
    _assert_invariant(t)


def test_lobby_seeds_open_tournaments_one_slot_short():
    pools = tournament.generate_tournament_lobby(random.Random(1))
    assert len(pools) >= 3
    assert {t.format for t in pools} == {"leaderboard_pool", "single_elim"}  # both formats seeded
    for t in pools:
        assert t.status == "OPEN"
        assert len(t.entrants) == t.max_entrants - 1  # last seat open for the player
        assert all(e.player_id.startswith("bot_") for e in t.entrants)


# --------------------------------------------------------------------------- #
# Single-elimination brackets
# --------------------------------------------------------------------------- #

def _make_elim(entry_fee=10.0, rake_pct=0.10, max_entrants=8, min_entrants=2,
               prize_split=None) -> Tournament:
    t = tournament.create_tournament(
        "chess.lichess", "Knockout", "chess_accuracy_pct", entry_fee=entry_fee,
        fmt="single_elim", rake_pct=rake_pct, max_entrants=max_entrants,
        min_entrants=min_entrants, prize_split=prize_split or [0.6, 0.3, 0.1],
    )
    return t


def test_seed_order_spreads_top_seeds():
    # Size 4: 1v4, 2v3 → 0-indexed [0, 3, 1, 2].
    assert tournament._seed_order(4) == [0, 3, 1, 2]
    # Size 8: top two seeds land in opposite halves (meet only in the final).
    order = tournament._seed_order(8)
    assert sorted(order) == list(range(8))
    assert order.index(0) < 4 and order.index(1) >= 4


def test_single_elim_produces_one_champion_and_holds_invariant():
    t = _make_elim(entry_fee=10.0)
    for p in ("a", "b", "c", "d"):
        _enter(t, p)
    scores = {"a": 95, "b": 85, "c": 75, "d": 65}
    telemetry = {p: _tel(s) for p, s in scores.items()}
    tournament.settle_tournament(t, telemetry, rng=random.Random(7))

    assert t.status == "SETTLED"
    assert t.rounds  # bracket was played out
    champions = [e for e in t.entrants if e.rank == 1]
    assert len(champions) == 1 and champions[0].status == "PAID"
    assert champions[0].detail == "Champion"
    # Every non-bye match resolved to one of its two players.
    for rnd in t.rounds:
        for m in rnd:
            if m.player_a and m.player_b:
                assert m.winner in (m.player_a, m.player_b)
                assert m.games >= 1
    _assert_invariant(t)


def test_single_elim_handles_byes_for_non_power_of_two():
    t = _make_elim(prize_split=[1.0])
    for p in ("a", "b", "c"):  # 3 players → bracket of 4 with one bye
        _enter(t, p)
    tournament.settle_tournament(t, {p: _tel(80 - i * 5) for i, p in enumerate(("a", "b", "c"))}, rng=random.Random(3))
    ranks = sorted(e.rank for e in t.entrants if e.rank is not None)
    assert ranks == [1, 2, 3]  # distinct placements, no crash on the bye
    # The bye match carries the "bye" marker.
    assert any(m.detail == "bye" for rnd in t.rounds for m in rnd)
    _assert_invariant(t)


def test_single_elim_needs_two_verifiable_else_refunds():
    t = _make_elim(entry_fee=10.0)
    for p in ("a", "b", "c"):
        _enter(t, p)
    # Only one entrant reports telemetry → cannot form a match → refund all.
    tournament.settle_tournament(t, {"a": _tel(90)}, rng=random.Random(1))
    assert t.status == "SETTLED"
    assert all(e.status == "REFUNDED" for e in t.entrants)
    assert t.rake == 0.0
    _assert_invariant(t)


def test_play_match_rematches_on_draw():
    rng = random.Random(0)
    strengths = {"a": 80.0, "b": 80.0}
    # Force a draw then a decisive game by controlling the RNG stream is fiddly;
    # instead assert the contract: a winner is one of the pair, >=1 game played.
    seen_multi_game = False
    for seed in range(50):
        winner, games = tournament._play_match("a", "b", strengths, random.Random(seed))
        assert winner in ("a", "b")
        assert 1 <= games <= tournament._MAX_GAMES
        seen_multi_game = seen_multi_game or games > 1
    assert seen_multi_game  # at least one draw forced a rematch across 50 seeds


@pytest.mark.parametrize("seed", range(25))
def test_single_elim_invariant_under_random_fields(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 9)
    t = _make_elim(
        entry_fee=rng.choice([1.0, 5.0, 10.0, 25.0]),
        rake_pct=rng.choice([0.05, 0.10, 0.15]),
        max_entrants=10,
        prize_split=rng.choice([[1.0], [0.6, 0.4], [0.6, 0.3, 0.1]]),
    )
    for i in range(n):
        _enter(t, f"p{i}")
    telemetry = {}
    for i in range(n):
        if rng.random() < 0.15:  # some un-verifiable entrants
            continue
        telemetry[f"p{i}"] = _tel(rng.uniform(40, 99))
    tournament.settle_tournament(t, telemetry, rng=random.Random(seed + 100))
    _assert_invariant(t)
