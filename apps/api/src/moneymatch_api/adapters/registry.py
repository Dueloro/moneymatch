"""Adapter registry. Callers resolve adapters by game id, never by import
(00-README §3.5). Ported from poc-reference + a feature-flag filter and dropping
the dead `stub_cs2`.

The registry knows every *built* adapter; whether a game is currently linkable is
a runtime decision driven by the `game:<id>` feature flag (05-phase-2 · disabling
a game hides it from linking and marks it BLOCKED on Profile). Flags are read
from the DB by the caller and passed in, so the registry stays pure/importable.
"""

from __future__ import annotations

from ..constants import game_flag_key
from .base import GameAdapter
from .chess_lichess import ChessLichessAdapter
from .cs2_faceit import CS2FaceitAdapter
from .cs2_steam import CS2SteamAdapter
from .dota2_opendota import Dota2OpenDotaAdapter
from .pubg import PubgAdapter

_ADAPTERS: dict[str, GameAdapter] = {
    ChessLichessAdapter.id: ChessLichessAdapter(),
    CS2FaceitAdapter.id: CS2FaceitAdapter(),
    CS2SteamAdapter.id: CS2SteamAdapter(),
    Dota2OpenDotaAdapter.id: Dota2OpenDotaAdapter(),
    PubgAdapter.id: PubgAdapter(),
}

DEFAULT_GAME = ChessLichessAdapter.id


def get(game_id: str) -> GameAdapter:
    """Resolve the adapter for a game id, or raise `ValueError` if unregistered.

    When `DEMO_SIMULATE_ENABLED` is set the adapter is wrapped so injected demo
    matches appear alongside real host history. Every consumer of match history
    resolves through here, which is what lets a simulated result settle a wager
    without a single `if simulated` branch downstream. With the flag off the
    untouched adapter is returned and the wrapper is never constructed.
    """
    try:
        adapter = _ADAPTERS[game_id]
    except KeyError:
        raise ValueError(f"No adapter registered for game '{game_id}'") from None

    from ..services import demo_simulation

    if demo_simulation.is_enabled():
        from .simulated import SimulatedGamesAdapter

        return SimulatedGamesAdapter(adapter)
    return adapter


def all_ids() -> list[str]:
    """Every built adapter id, regardless of feature flags."""
    return list(_ADAPTERS.keys())


def is_enabled(game_id: str, flags: dict[str, bool]) -> bool:
    """Whether a game is currently linkable (its `game:<id>` flag is on).

    Unknown / unset flag defaults to enabled — the migration seeds every game
    flag on, so an absent key means "not explicitly disabled".
    """
    if game_id not in _ADAPTERS:
        return False
    return flags.get(game_flag_key(game_id), True)


def enabled_ids(flags: dict[str, bool]) -> list[str]:
    """Built adapter ids whose feature flag is enabled."""
    return [gid for gid in _ADAPTERS if is_enabled(gid, flags)]
