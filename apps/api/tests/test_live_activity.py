"""Live under-the-card snapshots for in-flight H2H matches (build + orient)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services import live_activity_service
from moneymatch_api.services.hosts import lichess

CHESS = "chess.lichess"


def _window():
    now = datetime.now(UTC)
    return now - timedelta(minutes=10), now + timedelta(hours=1)


def _seat(user_id, host, color=None):
    return MatchPlayer(user_id=user_id, host_account_id=host, color=color)


async def test_chess_live_snapshot_orients_turn_and_moves(monkeypatch):
    start, end = _window()
    u_white, u_black = uuid.uuid4(), uuid.uuid4()
    match = Match(
        game=CHESS,
        market="win_h2h",
        host_game_id="g123",
        matched_at=start,
        window_ends_at=end,
    )
    seats = [_seat(u_white, "alice", "white"), _seat(u_black, "bob", "black")]

    async def fake_live(game_id):
        assert game_id == "g123"
        return {
            "status": "started",
            "moves": "e4 e5 Nf3",
            "winner": None,
            "players": {
                "white": {"user": {"name": "alice"}},
                "black": {"user": {"name": "bob"}},
            },
        }

    monkeypatch.setattr(lichess, "get_live_game", fake_live)

    snap = await live_activity_service.build_match_snapshot(None, match, seats)
    assert snap["format"] == "chess" and snap["status"] == "live"
    assert snap["moves"] == 2

    white_view = live_activity_service.view_for("match", snap, u_white)
    black_view = live_activity_service.view_for("match", snap, u_black)
    assert white_view["your_color"] == "white" and white_view["turn"] == "opp"
    assert black_view["your_color"] == "black" and black_view["turn"] == "you"
    assert white_view["result"] is None


async def test_chess_finished_maps_result_per_viewer(monkeypatch):
    start, end = _window()
    u_white, u_black = uuid.uuid4(), uuid.uuid4()
    match = Match(
        game=CHESS,
        market="win_h2h",
        host_game_id="g9",
        matched_at=start,
        window_ends_at=end,
    )
    seats = [_seat(u_white, "alice", "white"), _seat(u_black, "bob", "black")]

    async def fake_live(game_id):
        return {
            "status": "mate",
            "moves": "e4 e5 Qh5 Nc6 Bc4 Nf6 Qxf7",
            "winner": "white",
            "players": {
                "white": {"user": {"name": "alice"}},
                "black": {"user": {"name": "bob"}},
            },
        }

    monkeypatch.setattr(lichess, "get_live_game", fake_live)
    snap = await live_activity_service.build_match_snapshot(None, match, seats)
    assert snap["status"] == "finished"
    assert live_activity_service.view_for("match", snap, u_white)["result"] == "you"
    assert live_activity_service.view_for("match", snap, u_black)["result"] == "opp"


async def test_no_snapshot_before_pairing():
    match = Match(game=CHESS, market="win_h2h", matched_at=None)
    assert await live_activity_service.build_match_snapshot(None, match, []) is None


def test_board_fields_only_on_the_match_stage_view():
    viewer = uuid.uuid4()
    snap = live_activity_service.snapshot_from_live(
        {
            "finished": True,
            "moves": 1,
            "plies": 1,
            "turn": None,
            "winner": "white",
            "termination": "resignation",
            "san": ["e4"],
            "clocks": {"white_ms": 1, "black_ms": 2},
            "clock": {"limit": 60, "increment": 0},
            "last_move_at": 1_760_000_000_000,
        },
        [_seat(viewer, "alice", "white")],
    )
    feed = live_activity_service.view_for("match", snap, viewer)
    stage = live_activity_service.view_for("match", snap, viewer, board=True)
    assert feed["termination"] == "resignation" and "san" not in feed
    assert stage["san"] == ["e4"] and stage["last_move_at"].startswith("2025-")
