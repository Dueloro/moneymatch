"""Live under-the-card snapshots for in-flight H2H matches (build + orient).

Pure unit tests: models are built in-memory (never flushed) and the host reads
are faked, so this covers the snapshot shape and the per-viewer orientation
without a database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services import live_activity_service
from moneymatch_api.services.hosts import lichess

pytestmark = pytest.mark.asyncio

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
            "moves": "e4 e5 Nf3",  # 3 plies → black to move; 2 full moves
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
    assert white_view["result"] is None  # ongoing


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
    """A match with no live window yet (unpaired) has no live view."""
    match = Match(game=CHESS, market="win_h2h", matched_at=None)
    assert await live_activity_service.build_match_snapshot(None, match, []) is None
