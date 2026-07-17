"""Market definitions — the fixed, per-game list of what you can wager on.

Static Python config (no DB — Phase 3 deliverable 1): each `MarketDef` is a
game → market mapping with its **resolution rule**. There are **no free-form
props** (legal guardrail, 01-architecture §3.1) and **no odds** — the on-screen
multiplier is derived pot math (`2·(1 − rake)`), never a configured line
(02-design-system §4).

Resolution kinds:
- `win_h2h`  — chess only; brokered Lichess game between the two bound accounts,
  graded by game id; draw → push.
- `win_next` — each player's first finished match after `matched_at`; win beats
  loss; both-win / both-lose / tie → push.
- `stat_race` — each player's rate stat (`metric`) from their first finished
  match after `matched_at`; higher wins; equal → push.

`metric` (stat races only) is the `metric_models` key that gates eligibility
(provisional metrics can't back a duel) and grades the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import (
    GAME_CHESS_LICHESS,
    GAME_CS2_FACEIT,
    GAME_DOTA2_OPENDOTA,
)
from . import money_math

# Resolution kinds (see module docstring).
KIND_WIN_H2H = "win_h2h"
KIND_WIN_NEXT = "win_next"
KIND_STAT_RACE = "stat_race"


@dataclass(frozen=True)
class MarketDef:
    game: str
    key: str  # the market id used in requests (e.g. "kd_ratio", "win_h2h")
    label: str  # design copy for the market row
    kind: str  # KIND_WIN_H2H | KIND_WIN_NEXT | KIND_STAT_RACE
    metric: str | None = None  # metric_models key (stat races only)
    requires_speed: bool = False  # chess needs a time control
    rake_bps: int = money_math.DEFAULT_RAKE_BPS

    @property
    def brokered(self) -> bool:
        """Whether the platform creates the game (chess) vs. players coordinate."""
        return self.kind == KIND_WIN_H2H

    @property
    def multiplier_bps(self) -> int:
        """Derived H2H display multiplier (basis points): 2·(1 − rake)."""
        return money_math.h2h_multiplier_bps(self.rake_bps)


# The canonical market list, in design order per game (design PDF p.1).
MARKETS: tuple[MarketDef, ...] = (
    # Chess — brokered head-to-head, one market per time control.
    MarketDef(
        game=GAME_CHESS_LICHESS,
        key="win_h2h",
        label="Win the game",
        kind=KIND_WIN_H2H,
        requires_speed=True,
    ),
    # CS2 — stat duels + next-match win.
    MarketDef(
        game=GAME_CS2_FACEIT,
        key="kd_ratio",
        label="K/D ratio",
        kind=KIND_STAT_RACE,
        metric="cs2_kd_ratio",
    ),
    MarketDef(
        game=GAME_CS2_FACEIT,
        key="adr",
        label="ADR",
        kind=KIND_STAT_RACE,
        metric="cs2_adr",
    ),
    MarketDef(
        game=GAME_CS2_FACEIT,
        key="headshot_pct",
        label="Headshot %",
        kind=KIND_STAT_RACE,
        metric="cs2_headshot_pct",
    ),
    MarketDef(
        game=GAME_CS2_FACEIT,
        key="win_next",
        label="Win your next match",
        kind=KIND_WIN_NEXT,
    ),
    # Dota 2 — next-match win + stat duels.
    MarketDef(
        game=GAME_DOTA2_OPENDOTA,
        key="win_next",
        label="Win your next match",
        kind=KIND_WIN_NEXT,
    ),
    MarketDef(
        game=GAME_DOTA2_OPENDOTA,
        key="kda_ratio",
        label="KDA ratio",
        kind=KIND_STAT_RACE,
        metric="dota2_kda_ratio",
    ),
    MarketDef(
        game=GAME_DOTA2_OPENDOTA,
        key="gpm",
        label="GPM",
        kind=KIND_STAT_RACE,
        metric="dota2_gpm",
    ),
)

_BY_GAME_KEY: dict[tuple[str, str], MarketDef] = {(m.game, m.key): m for m in MARKETS}


def get(game: str, key: str) -> MarketDef | None:
    """Resolve a market def by game + key, or None if it isn't offered."""
    return _BY_GAME_KEY.get((game, key))


def for_game(game: str) -> list[MarketDef]:
    """Every market offered for a game, in design order."""
    return [m for m in MARKETS if m.game == game]
