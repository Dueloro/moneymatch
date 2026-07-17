"""chess.lichess adapter — profile mapping, normalization, and brokered-game
integrity (`match_winner` only grades a game between our two accounts).
Host calls respx-mocked."""

from __future__ import annotations

import httpx
import pytest
import respx

from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter

ADAPTER = ChessLichessAdapter()
USER_URL = "https://lichess.org/api/user/magnus"


def _user(**over):
    base = {
        "id": "magnus",
        "username": "Magnus",
        "url": "https://lichess.org/@/Magnus",
        "createdAt": 1_300_000_000_000,
        "perfs": {
            "blitz": {"rating": 2800, "games": 500, "prov": False},
            "bullet": {"rating": 2900, "games": 1200},
        },
        "count": {"rated": 1700, "win": 1000, "draw": 200, "loss": 500},
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Profile mapping
# --------------------------------------------------------------------------- #


def test_maps_lichess_user_into_profile():
    p = ADAPTER._to_profile(_user())
    assert p.game == "chess.lichess"
    assert p.username == "Magnus"
    assert p.primary_speed == "bullet"  # most games
    assert {f.speed for f in p.formats} == {"blitz", "bullet"}
    assert p.total_games == 1700
    assert p.win_rate == round((1000 + 0.5 * 200) / 1700, 4)


def test_normalize_marks_user_win_and_skips_others():
    game = {
        "id": "g1",
        "status": "mate",
        "speed": "blitz",
        "rated": True,
        "createdAt": 10_000,
        "winner": "white",
        "moves": "e4 e5 Qh5",
        "players": {
            "white": {"user": {"id": "magnus"}},
            "black": {"user": {"id": "rival"}},
        },
    }
    norm = ADAPTER._normalize(game, "magnus")
    assert norm is not None and norm.won is True and norm.moves == 2

    # A game the user isn't in is skipped.
    assert ADAPTER._normalize(game, "stranger") is None


def test_normalize_draw_is_not_a_win():
    game = {
        "id": "g2",
        "status": "draw",
        "speed": "blitz",
        "rated": True,
        "createdAt": 1,
        "winner": None,
        "players": {
            "white": {"user": {"id": "magnus"}},
            "black": {"user": {"id": "rival"}},
        },
    }
    norm = ADAPTER._normalize(game, "magnus")
    assert norm.drawn is True and norm.won is False


# --------------------------------------------------------------------------- #
# fetch_profile + brokered-game integrity
# --------------------------------------------------------------------------- #


@respx.mock
async def test_fetch_profile_end_to_end():
    respx.get(USER_URL).mock(return_value=httpx.Response(200, json=_user()))
    p = await ADAPTER.link_account("username", "magnus")
    assert p.username == "Magnus" and p.link_method == "username"


@respx.mock
async def test_fetch_profile_unknown_user_raises():
    respx.get("https://lichess.org/api/user/ghost").mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(ValueError, match="not found"):
        await ADAPTER.fetch_profile("ghost")


@respx.mock
async def test_match_winner_requires_both_our_accounts():
    game = {
        "status": "mate",
        "winner": "white",
        "players": {
            "white": {"user": {"name": "alice"}},
            "black": {"user": {"name": "bob"}},
        },
    }
    respx.get("https://lichess.org/game/export/g1").mock(
        return_value=httpx.Response(200, json=game)
    )
    # Winner is our player "alice".
    assert await ADAPTER.match_winner("g1", ["alice", "bob"]) == "alice"
    # An outsider replacing a seat → unverifiable (integrity guard).
    assert await ADAPTER.match_winner("g1", ["alice", "carol"]) is None
