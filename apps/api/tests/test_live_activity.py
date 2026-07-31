"""Live under-the-card snapshots for in-flight H2H matches (build + orient).

Pure unit tests: models are built in-memory (never flushed) and the host reads
are faked, so this covers the snapshot shape and the per-viewer orientation
without a database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services import live_activity_service
from moneymatch_api.services.hosts import lichess

pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
KD = "cs2_kd_ratio"


def _window():
    now = datetime.now(UTC)
    return now - timedelta(minutes=10), now + timedelta(hours=1)


def _seat(user_id, host, color=None):
    return MatchPlayer(user_id=user_id, host_account_id=host, color=color)


async def test_chess_live_snapshot_orients_turn_and_moves(monkeypatch):
    start, end = _window()
    u_white, u_black = uuid.uuid4(), uuid.uuid4()
    match = Match(
        game="chess.lichess",
        market="win_h2h",
        brokered=True,
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

    snap = await live_activity_service.build_match_snapshot(match, seats)
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
        game="chess.lichess",
        market="win_h2h",
        brokered=True,
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
    snap = await live_activity_service.build_match_snapshot(match, seats)
    assert snap["status"] == "finished"
    assert live_activity_service.view_for("match", snap, u_white)["result"] == "you"
    assert live_activity_service.view_for("match", snap, u_black)["result"] == "opp"


class _FakeAdapter:
    id = CS2
    brokered = False

    def __init__(self, games):
        self.games = games

    async def poll_eligible_games(self, host, since_ms, filters):
        return self.games.get(host, [])


def _game(ms, kd):
    return NormGame(
        id=f"m{ms}",
        speed="cs2",
        rated=True,
        created_at_ms=ms,
        moves=0,
        won=None,
        drawn=False,
        metrics={KD: kd},
    )


async def test_stat_race_snapshot_leader_per_viewer(monkeypatch):
    start, end = _window()
    u_you, u_opp = uuid.uuid4(), uuid.uuid4()
    match = Match(
        game=CS2,
        market="kd_ratio",
        brokered=False,
        host_game_id=None,
        matched_at=start,
        window_ends_at=end,
    )
    seats = [_seat(u_you, "alice"), _seat(u_opp, "bob")]
    mid = int((start + timedelta(minutes=5)).timestamp() * 1000)
    games = {"alice": [_game(mid, 1.6)], "bob": [_game(mid, 1.2)]}
    monkeypatch.setattr(registry, "get", lambda g: _FakeAdapter(games))

    snap = await live_activity_service.build_match_snapshot(match, seats)
    assert snap["format"] == "stat_race" and snap["status"] == "live"

    you_view = live_activity_service.view_for("match", snap, u_you)
    opp_view = live_activity_service.view_for("match", snap, u_opp)
    assert you_view["you"] == 1.6 and you_view["opp"] == 1.2
    assert you_view["leader"] == "you"
    assert opp_view["you"] == 1.2 and opp_view["leader"] == "opp"


async def test_no_snapshot_before_pairing():
    """A match with no live window yet (unpaired) has no live view."""
    match = Match(game=CS2, market="kd_ratio", brokered=False, matched_at=None)
    assert await live_activity_service.build_match_snapshot(match, []) is None
