"""Casual games must never reach anything that builds or grades a stat."""

from __future__ import annotations

import pytest

from moneymatch_api.adapters.base import GameFilters
from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter

pytestmark = pytest.mark.nodb


def _raw(game_id: str, rated: bool) -> dict:
    return {
        "id": game_id,
        "rated": rated,
        "variant": "standard",
        "speed": "bullet",
        "status": "mate",
        "createdAt": 1_785_963_612_475,
        "winner": "white",
        "moves": "e4 e5 Qh5 Nc6 Bc4 Nf6 Qxf7#",
        "players": {
            "white": {"user": {"id": "me", "name": "me"}},
            "black": {"user": {"id": "them", "name": "them"}},
        },
    }


@pytest.fixture
def patched_host(monkeypatch):
    seen: dict[str, object] = {}
    games = [_raw("rated1", True), _raw("casual1", False), _raw("rated2", True)]

    async def fake_get_user_games(
        username, since_ms, perf_types=None, max_games=50, rated_only=True
    ):
        seen["rated_only"] = rated_only
        return [g for g in games if g["rated"]] if rated_only else games

    monkeypatch.setattr(
        "moneymatch_api.adapters.chess_lichess.lichess.get_user_games",
        fake_get_user_games,
    )
    return seen


async def test_default_filters_are_rated_only(patched_host):
    out = await ChessLichessAdapter().poll_eligible_games("me", 0, GameFilters())

    assert patched_host["rated_only"] is True
    assert [g.id for g in out] == ["rated1", "rated2"]
    assert all(g.rated for g in out)


async def test_casual_games_are_dropped_even_if_the_host_returns_them(monkeypatch):

    async def leaky_get_user_games(
        username, since_ms, perf_types=None, max_games=50, rated_only=True
    ):
        return [_raw("rated1", True), _raw("casual1", False)]

    monkeypatch.setattr(
        "moneymatch_api.adapters.chess_lichess.lichess.get_user_games",
        leaky_get_user_games,
    )
    out = await ChessLichessAdapter().poll_eligible_games("me", 0, GameFilters())
    assert [g.id for g in out] == ["rated1"]


async def test_opting_out_returns_casual_games_too(patched_host):
    out = await ChessLichessAdapter().poll_eligible_games(
        "me", 0, GameFilters(rated_only=False)
    )

    assert patched_host["rated_only"] is False
    assert [g.id for g in out] == ["rated1", "casual1", "rated2"]


async def test_the_metric_still_lands_on_the_kept_games(patched_host):
    out = await ChessLichessAdapter().poll_eligible_games("me", 0, GameFilters())
    assert all(g.metrics["chess_moves"] == 4.0 for g in out)
