"""Adapter registry. Callers resolve adapters by game id, never by import."""

from __future__ import annotations

from ..constants import game_flag_key
from .base import GameAdapter
from .chess_lichess import ChessLichessAdapter

_ADAPTERS: dict[str, GameAdapter] = {
    ChessLichessAdapter.id: ChessLichessAdapter(),
}

DEFAULT_GAME = ChessLichessAdapter.id


def get(game_id: str) -> GameAdapter:
    """Resolve the adapter for a game id, or raise `ValueError` if unregistered."""
    try:
        return _ADAPTERS[game_id]
    except KeyError:
        raise ValueError(f"No adapter registered for game '{game_id}'") from None


def all_ids() -> list[str]:
    """Every built adapter id, regardless of feature flags."""
    return list(_ADAPTERS.keys())


def is_enabled(game_id: str, flags: dict[str, bool]) -> bool:
    """Whether a game is currently linkable (its `game:<id>` flag is on)."""
    if game_id not in _ADAPTERS:
        return False
    return flags.get(game_flag_key(game_id), True)


def enabled_ids(flags: dict[str, bool]) -> list[str]:
    return [gid for gid in _ADAPTERS if is_enabled(gid, flags)]
