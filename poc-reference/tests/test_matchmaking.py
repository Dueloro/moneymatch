"""Tests for the in-memory matchmaking queue (api/_lib/match_queue.py)."""

import pytest

from _lib import match_queue
from _lib.schemas import QueueRequest


@pytest.fixture(autouse=True)
def _clean():
    match_queue.reset()
    yield
    match_queue.reset()


def _req(pid, game="chess.lichess", speed="blitz", fmt="Rated Blitz", entry=10.0, rating=1500):
    return QueueRequest(player_id=pid, display_name=pid, game=game, speed=speed,
                        format=fmt, entry=entry, rating=rating)


def test_first_searches_second_matches():
    assert match_queue.enqueue(_req("alice")).status == "searching"
    r = match_queue.enqueue(_req("bob"))
    assert r.status == "matched"
    m = r.match
    assert {p.player_id for p in m.players} == {"alice", "bob"}
    assert m.state == "PENDING" and m.entry == 10.0
    # Both players now poll to "matched".
    assert match_queue.poll("alice").status == "matched"
    assert match_queue.poll("bob").status == "matched"


def test_incompatible_entry_does_not_pair():
    match_queue.enqueue(_req("alice", entry=10.0))
    assert match_queue.enqueue(_req("bob", entry=25.0)).status == "searching"


def test_far_rating_does_not_pair_immediately():
    match_queue.enqueue(_req("alice", rating=1200))
    # 1200 vs 2600 is far beyond the fresh band → no pairing yet.
    assert match_queue.enqueue(_req("bob", rating=2600)).status == "searching"


def test_chess_is_brokered_with_colors():
    match_queue.enqueue(_req("alice"))
    m = match_queue.enqueue(_req("bob")).match
    assert m.brokered is True
    assert {p.color for p in m.players} == {"white", "black"}


def test_cs2_is_coordinated_no_colors():
    match_queue.enqueue(_req("alice", game="cs2.faceit", speed="cs2", fmt="Competitive"))
    m = match_queue.enqueue(_req("bob", game="cs2.faceit", speed="cs2", fmt="Competitive")).match
    assert m.brokered is False
    assert all(p.color is None for p in m.players)


def test_confirm_activate_and_settle_pays_winner():
    match_queue.enqueue(_req("alice"))
    m = match_queue.enqueue(_req("bob")).match
    match_queue.confirm(m.id, "alice")
    m = match_queue.confirm(m.id, "bob")
    assert match_queue.both_confirmed(m)
    match_queue.activate(m, {"game_id": "g1", "urls": {"white": "u/w", "black": "u/b"}})
    assert m.state == "ACTIVE" and m.host_game_id == "g1"
    white = next(p for p in m.players if p.color == "white")
    assert white.play_url == "u/w"

    match_queue.finalize(m, "alice")
    assert m.state == "SETTLED" and m.winner_id == "alice"
    payouts = {p.player_id: p.payout for p in m.players}
    assert payouts["alice"] == m.prize and payouts["bob"] == 0.0
    # Invariant: winner prize + loser 0 + rake == pot.
    assert round(payouts["alice"] + payouts["bob"] + m.rake, 2) == m.pot


def test_draw_refunds_both_no_rake():
    match_queue.enqueue(_req("alice"))
    m = match_queue.enqueue(_req("bob")).match
    match_queue.finalize(m, None)  # draw / void
    assert m.state == "CANCELED" and m.outcome == "refunded"
    assert all(p.payout == m.entry for p in m.players)
    # Every entry returned, so payouts == entries and no rake is taken.
    assert round(sum(p.payout for p in m.players), 2) == round(m.entry * 2, 2)


def test_cancel_pending_refunds_and_frees_players():
    match_queue.enqueue(_req("alice"))
    m = match_queue.enqueue(_req("bob")).match
    canceled = match_queue.cancel("alice")
    assert canceled.state == "CANCELED"
    # Both are freed from the match afterward.
    assert match_queue.poll("alice").status == "idle"
    assert match_queue.poll("bob").status == "idle"


def test_econ_prize_plus_rake_equals_pot():
    match_queue.enqueue(_req("alice", entry=7.5))
    m = match_queue.enqueue(_req("bob", entry=7.5)).match
    assert round(m.prize + m.rake, 2) == m.pot == 15.0
