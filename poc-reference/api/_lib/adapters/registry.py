"""Adapter registry. Callers resolve adapters by game id, never by import."""

from __future__ import annotations

from _lib.adapters.base import GameAdapter
from _lib.adapters.chess_lichess import ChessLichessAdapter
from _lib.adapters.cs2_faceit import CS2FaceitAdapter
from _lib.adapters.dota2_opendota import Dota2OpenDotaAdapter

# Live games: Chess (Lichess), CS2 (FaceIt), Dota 2 (OpenDota). Each provides
# verified identity, pooled play, and head-to-head settlement against the host's
# real match history (roadmap §5 multi-game expansion).
_ADAPTERS: dict[str, GameAdapter] = {
    ChessLichessAdapter.id: ChessLichessAdapter(),
    CS2FaceitAdapter.id: CS2FaceitAdapter(),
    Dota2OpenDotaAdapter.id: Dota2OpenDotaAdapter(),
}

DEFAULT_GAME = ChessLichessAdapter.id


def get(game_id: str) -> GameAdapter:
    try:
        return _ADAPTERS[game_id]
    except KeyError:
        raise ValueError(f"No adapter registered for game '{game_id}'")


def ids() -> list[str]:
    return list(_ADAPTERS.keys())
