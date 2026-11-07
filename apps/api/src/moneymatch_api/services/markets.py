"""Market definitions: the fixed list of what you can wager on.

Chess offers one market, `win_h2h`: a Lichess game between the two bound
accounts, graded by game id; draw → push. No props, no odds.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import GAME_CHESS_LICHESS
from . import money_math

KIND_WIN_H2H = "win_h2h"


@dataclass(frozen=True)
class MarketDef:
    game: str
    key: str  # the market id used in requests
    label: str
    kind: str
    requires_speed: bool = False  # chess needs a time control
    rake_bps: int = money_math.DEFAULT_RAKE_BPS

    @property
    def multiplier_bps(self) -> int:
        """Derived H2H display multiplier (basis points): 2·(1 − rake)."""
        return money_math.h2h_multiplier_bps(self.rake_bps)


MARKETS: tuple[MarketDef, ...] = (
    MarketDef(
        game=GAME_CHESS_LICHESS,
        key="win_h2h",
        label="Win the game",
        kind=KIND_WIN_H2H,
        requires_speed=True,
    ),
)

_BY_GAME_KEY: dict[tuple[str, str], MarketDef] = {(m.game, m.key): m for m in MARKETS}


def get(game: str, key: str) -> MarketDef | None:
    """Resolve a market def by game + key, or None if it isn't offered."""
    return _BY_GAME_KEY.get((game, key))


def for_game(game: str) -> list[MarketDef]:
    """Every market offered for a game."""
    return [m for m in MARKETS if m.game == game]
