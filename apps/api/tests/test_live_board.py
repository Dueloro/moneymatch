"""Live board + settle timing: the Lichess export (moves, clocks, status) flows
through grading into the stored snapshot, the match view, and the settlement
record; termination maps to a stable enum; the searching status recaps the ticket.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter, termination_of
from moneymatch_api.models.live import LiveSnapshot
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services.hosts import lichess
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
    _serve(monkeypatch, _game(status="aborted", moves=""))

    report = await settlement_worker.run_cycle(sm)
    assert report.canceled == 1
    async with sm() as s:
        match = await s.get(Match, match_id)
        assert match.state == "CANCELED"
        assert match.outcome_detail["reason"] == "game_aborted"


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
