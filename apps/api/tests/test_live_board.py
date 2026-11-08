"""Live board + settle timing: the Lichess export (moves, clocks, status) flows
through grading into the stored snapshot, the match view, and the settlement
record; termination maps to a stable enum; the searching status recaps the ticket.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter, termination_of
from moneymatch_api.models.live import LiveSnapshot
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services import reconciliation_service, wallet_service
from moneymatch_api.services.hosts import lichess
from moneymatch_api.services.hosts.errors import HostRateLimited
from moneymatch_api.workers import settlement_worker

from .conftest import new_sessionmaker
from .test_play_endpoints import CHESS, V1, _hdr, _queue, setup_player

ADAPTER = ChessLichessAdapter()
ENDED_MS = 1_760_000_000_000


def _game(status="started", moves="e4 e5 Nf3", winner=None, white="alice", **over):
    black = "bob" if white == "alice" else "alice"
    g = {
        "status": status,
        "moves": moves,
        "clock": {"initial": 300, "increment": 0, "totalTime": 300},
        "clocks": [30003, 30003, 29500, 29100, 28000][: len(moves.split())],
        "lastMoveAt": ENDED_MS,
        "speed": "blitz",
        "players": {
            "white": {"user": {"name": white}},
            "black": {"user": {"name": black}},
        },
    }
    if winner:
        g["winner"] = winner
    g.update(over)
    return g


def _serve(monkeypatch, game):
    async def fake(game_id):
        return game

    monkeypatch.setattr(lichess, "get_live_game", fake)
    monkeypatch.setattr(lichess, "get_game_for_grading", fake, raising=False)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("mate", "checkmate"),
        ("resign", "resignation"),
        ("outoftime", "time"),
        ("draw", "draw"),
        ("insufficientMaterialClaim", "draw"),
        ("stalemate", "stalemate"),
        ("timeout", "abandoned"),
        ("aborted", "aborted"),
        ("noStart", "aborted"),
        ("cheat", "other"),
        ("started", None),
    ],
)
def test_termination_enum(status, expected):
    assert termination_of(status) == expected


async def test_live_match_carries_moves_and_clocks(monkeypatch):
    _serve(monkeypatch, _game())
    live = await ADAPTER.live_match("g1", ["alice", "bob"])
    assert live["san"] == ["e4", "e5", "Nf3"]
    # white moved twice (last 29500 cs), black once (30003 cs)
    assert live["clocks"] == {"white_ms": 295_000, "black_ms": 300_030}
    assert live["clock"] == {"limit": 300, "increment": 0}
    assert live["turn"] == "black" and live["termination"] is None


async def test_live_match_before_first_move_uses_the_initial_clock(monkeypatch):
    _serve(monkeypatch, _game(status="created", moves=""))
    live = await ADAPTER.live_match("g1", ["alice", "bob"])
    assert live["clocks"] == {"white_ms": 300_000, "black_ms": 300_000}
    assert live["plies"] == 0 and live["turn"] == "white"


async def test_match_result_maps_win_draw_and_abort(monkeypatch):
    _serve(monkeypatch, _game(status="resign", winner="black"))
    r = await ADAPTER.match_result("g1", ["Alice", "Bob"])
    assert r.finished and r.winner == "Bob"
    assert r.termination == "resignation" and r.ended_at_ms == ENDED_MS

    _serve(monkeypatch, _game(status="insufficientMaterialClaim"))
    r = await ADAPTER.match_result("g1", ["alice", "bob"])
    assert r.finished and r.winner == "" and r.termination == "draw"

    _serve(monkeypatch, _game(status="aborted", moves=""))
    r = await ADAPTER.match_result("g1", ["alice", "bob"])
    assert r.finished and r.winner is None and r.termination == "aborted"
    assert await ADAPTER.match_winner("g1", ["alice", "bob"]) is None


async def _active_match(client):
    await setup_player(client, "auth_a", "alice", host="alice")
    await setup_player(client, "auth_b", "bob", host="bob")
    await _queue(client, "auth_a")
    match_id = (await _queue(client, "auth_b")).json()["match"]["id"]
    await client.post(f"{V1}/play/matches/{match_id}/confirm", headers=_hdr("auth_a"))
    await client.post(f"{V1}/play/matches/{match_id}/confirm", headers=_hdr("auth_b"))
    sm = new_sessionmaker()
    async with sm() as s:
        seats = list(
            await s.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match_id))
        )
        alice_white = next(x for x in seats if x.host_account_id == "alice").color
    return sm, match_id, alice_white == "white"


async def _wallets(sm, match_id):
    """{host handle: (available, escrow)} for both seats."""
    async with sm() as s:
        seats = list(
            await s.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match_id))
        )
        out = {}
        for seat in seats:
            w = await wallet_service.get_wallet(s, seat.user_id)
            out[seat.host_account_id] = (w.available_cents, w.escrow_cents)
        return out


async def _state(sm, match_id):
    async with sm() as s:
        return await s.get(Match, match_id)


def _refunded(before, after):
    """Both seats back where they were before staking (1,000 each), escrow 0."""
    return all(after[h] == (before[h][0] + before[h][1], 0) for h in before)


async def test_grading_refreshes_the_board_and_the_view_orients_it(client, monkeypatch):
    sm, match_id, alice_white = await _active_match(client)
    _serve(monkeypatch, _game(white="alice" if alice_white else "bob"))

    report = await settlement_worker.run_cycle(sm)
    assert report.pending == 1

    body = (
        await client.get(f"{V1}/play/matches/{match_id}", headers=_hdr("auth_a"))
    ).json()
    live = body["live"]
    assert live["status"] == "live" and live["san"] == ["e4", "e5", "Nf3"]
    assert live["your_color"] == ("white" if alice_white else "black")
    assert live["clocks"]["white_ms"] == 295_000
    assert body["termination"] is None and body["game_ended_at"] is None

    # A board that stopped refreshing is withheld (the stage falls back to the link).
    async with sm() as s:
        row = await s.get(LiveSnapshot, ("match", match_id))
        row.updated_at = datetime.now(UTC) - timedelta(minutes=5)
        await s.commit()
    body = (
        await client.get(f"{V1}/play/matches/{match_id}", headers=_hdr("auth_a"))
    ).json()
    assert body["live"] is None


async def test_settlement_records_termination_and_timing(client, monkeypatch):
    sm, match_id, alice_white = await _active_match(client)
    finished = _game(
        status="outoftime",
        moves="e4 e5 Nf3 Nc6 Bb5",
        winner="white",
        white="alice" if alice_white else "bob",
        lastMoveAt=int(datetime.now(UTC).timestamp() * 1000) - 20_000,
    )
    _serve(monkeypatch, finished)

    report = await settlement_worker.run_cycle(sm)
    assert report.settled == 1

    body = (
        await client.get(f"{V1}/play/matches/{match_id}", headers=_hdr("auth_a"))
    ).json()
    assert body["state"] == "SETTLED"
    assert body["termination"] == "time"
    assert body["friendly"] is False
    assert (body["winner_user_id"] is not None) and body["players"]
    ended = datetime.fromisoformat(body["game_ended_at"])
    settled = datetime.fromisoformat(body["resolved_at"])
    assert timedelta(0) < settled - ended < timedelta(minutes=1)
    # The frozen final board survives settlement.
    assert body["live"]["status"] == "finished"
    assert body["live"]["result"] == ("you" if alice_white else "opp")
    assert len(body["live"]["san"]) == 5

    activity = (await client.get(f"{V1}/activity", headers=_hdr("auth_a"))).json()
    detail = next(i for i in activity["items"] if i["id"] == match_id)["detail"]
    assert detail["termination"] == "time" and detail["game_ended_at"]


async def test_aborted_game_cancels_and_refunds_promptly(client, monkeypatch):
    sm, match_id, _ = await _active_match(client)
    before = await _wallets(sm, match_id)
    _serve(monkeypatch, _game(status="aborted", moves=""))

    report = await settlement_worker.run_cycle(sm)
    assert report.canceled == 1
    match = await _state(sm, match_id)
    assert match.state == "CANCELED"
    assert match.outcome_detail["reason"] == "game_aborted"
    assert _refunded(before, await _wallets(sm, match_id))
    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", match_id)
        assert recon.ok and recon.totals["rake"] == 0


async def test_an_abort_after_moves_waits_for_the_deadline(client, monkeypatch):
    sm, match_id, _ = await _active_match(client)
    _serve(monkeypatch, _game(status="aborted", moves="e4 e5"))
    report = await settlement_worker.run_cycle(sm)
    assert report.pending == 1 and report.canceled == 0
    assert (await _state(sm, match_id)).state == "AWAITING_RESULT"


async def _past_deadline(sm, match_id):
    match = await _state(sm, match_id)
    return match.window_ends_at, match.window_ends_at + timedelta(seconds=5)


async def test_rate_limit_at_the_deadline_extends_the_window(client, monkeypatch):
    sm, match_id, _ = await _active_match(client)
    before = await _wallets(sm, match_id)
    ends, now = await _past_deadline(sm, match_id)

    async def limited(*args, **kwargs):
        raise HostRateLimited("lichess", "429", 429)

    monkeypatch.setattr(lichess, "request_json", limited)
    report = await settlement_worker.run_cycle(sm, now=now)
    assert report.pending == 1 and report.canceled == 0
    match = await _state(sm, match_id)
    assert match.state == "AWAITING_RESULT" and match.window_ends_at > ends
    assert await _wallets(sm, match_id) == before


async def test_a_malformed_body_counts_as_an_outage(client, monkeypatch):
    sm, match_id, _ = await _active_match(client)
    ends, now = await _past_deadline(sm, match_id)

    async def junk(*args, **kwargs):
        return httpx.Response(200, json=["not", "a", "game"])

    monkeypatch.setattr(lichess, "request_json", junk)
    report = await settlement_worker.run_cycle(sm, now=now)
    assert report.pending == 1
    assert (await _state(sm, match_id)).window_ends_at > ends


async def test_brokered_game_seats_white_first(client, monkeypatch):
    sent = {}

    async def capture(clock_limit, clock_increment=0, *, users=None):
        sent["users"] = users
        return {"game_id": "abcd1234", "urls": {}}

    monkeypatch.setattr(lichess, "create_open_challenge", capture)
    sm, match_id, alice_white = await _active_match(client)
    assert sent["users"][0] == ("alice" if alice_white else "bob")


async def test_colours_follow_the_game_actually_played(client, monkeypatch):
    sm, match_id, alice_white = await _active_match(client)
    # Lichess seated them the other way round from our seat colours.
    swapped = "bob" if alice_white else "alice"
    _serve(monkeypatch, _game(status="mate", winner="white", white=swapped))

    report = await settlement_worker.run_cycle(sm)
    assert report.settled == 1
    body = (
        await client.get(f"{V1}/play/matches/{match_id}", headers=_hdr("auth_a"))
    ).json()
    alice = next(p for p in body["players"] if p["is_you"])
    assert body["winner_user_id"] != alice["user_id"]
    assert body["live"]["your_color"] == ("black" if alice_white else "white")
    assert body["live"]["result"] == "opp"


async def test_no_start_with_a_winner_is_abandonment(client, monkeypatch):
    sm, match_id, alice_white = await _active_match(client)
    w = "alice" if alice_white else "bob"
    _serve(monkeypatch, _game(status="noStart", moves="", winner="white", white=w))
    report = await settlement_worker.run_cycle(sm)
    assert report.settled == 1
    match = await _state(sm, match_id)
    assert match.outcome_detail["termination"] == "abandoned"


@pytest.mark.parametrize(
    ("winner", "state"), [(None, "CANCELED"), ("white", "SETTLED")]
)
async def test_unknown_finish(client, monkeypatch, winner, state):
    sm, match_id, alice_white = await _active_match(client)
    w = "alice" if alice_white else "bob"
    _serve(monkeypatch, _game(status="unknownFinish", winner=winner, white=w))
    await settlement_worker.run_cycle(sm)
    match = await _state(sm, match_id)
    assert match.state == state
    if winner is None:
        assert match.outcome_detail["reason"] == "unknown_finish"


async def test_a_game_between_other_accounts_never_settles(client, monkeypatch):
    sm, match_id, _ = await _active_match(client)
    game = _game(status="mate", winner="white")
    game["players"]["black"]["user"]["name"] = "mallory"
    _serve(monkeypatch, game)
    report = await settlement_worker.run_cycle(sm)
    assert report.settled == 0 and report.pending == 1


@pytest.mark.parametrize("status", ["draw", "insufficientMaterialClaim", "stalemate"])
async def test_real_adapter_draw_refunds_exactly(client, monkeypatch, status):
    sm, match_id, alice_white = await _active_match(client)
    before = await _wallets(sm, match_id)
    w = "alice" if alice_white else "bob"
    _serve(monkeypatch, _game(status=status, moves="e4 e5 Nf3 Nc6", white=w))
    report = await settlement_worker.run_cycle(sm)
    assert report.pushed == 1
    assert _refunded(before, await _wallets(sm, match_id))
    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", match_id)
        assert recon.ok and recon.totals["rake"] == 0


async def test_winner_name_case_differs_from_the_bound_account(client, monkeypatch):
    sm, match_id, alice_white = await _active_match(client)
    before = await _wallets(sm, match_id)
    game = _game(status="resign", winner="white" if alice_white else "black")
    game["players"]["white"]["user"]["name"] = "ALICE" if alice_white else "BoB"
    game["players"]["black"]["user"]["name"] = "BoB" if alice_white else "ALICE"
    _serve(monkeypatch, game)
    report = await settlement_worker.run_cycle(sm)
    assert report.settled == 1
    after = await _wallets(sm, match_id)
    a0 = before["alice"][0] + before["alice"][1]
    b0 = before["bob"][0] + before["bob"][1]
    assert after["alice"] == (a0 + 800, 0)  # 1,800 prize on a 1,000 stake
    assert after["bob"] == (b0 - 1000, 0)


async def test_searching_status_recaps_the_ticket(client):
    await setup_player(client, "auth_s", "solo", rating=1640)
    await _queue(client, "auth_s", speed="rapid", entry=2500)
    body = (await client.get(f"{V1}/play/queue/status", headers=_hdr("auth_s"))).json()
    assert body["status"] == "searching"
    assert body["ticket"] == {
        "market": "win_h2h",
        "speed": "rapid",
        "clock": {"speed": "rapid", "limit_seconds": 600, "increment_seconds": 0},
        "entry_cents": 2500,
        "rating": 1640,
    }


async def test_markets_publish_each_speeds_clock(client):
    await setup_player(client, "auth_k", "clocky")
    body = (
        await client.get(
            f"{V1}/play/markets", params={"game": CHESS}, headers=_hdr("auth_k")
        )
    ).json()
    clocks = {c["speed"]: c for c in body["markets"][0]["clocks"]}
    assert clocks["blitz"] == {
        "speed": "blitz",
        "limit_seconds": 300,
        "increment_seconds": 0,
    }
    assert set(clocks) == {"bullet", "blitz", "rapid", "classical"}
