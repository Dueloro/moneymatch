"""The launch-scope bucket-market catalogue: a market = (game, mode, metric).

This is the single source of truth for *which* bucketed markets exist and how
each one behaves, taken verbatim from the Launch-scope table in
`IMPLEMENTATION_BUCKETING.md` / `BUCKETING_TECHNICAL_WALKTHROUGH.md`. It is a
**new, parallel** catalogue that sits beside the existing `services/markets.py`
(the current stat-duel/pool markets); the bucketing layer keys everything off
these `BucketMarket` rows and never mutates the legacy list.

Key differences from the legacy `constants.py` metric config, all deliberate and
straight from the spec:

- **CS2** rates on `cs2_kills` (primary) + `cs2_kd_ratio` (secondary); headshot %
  is dropped from wagering (own-volume percentage → exploitable). `cs2_score`
  is reserved for later.
- **Chess** is keyed **by speed**: `blitz` and `rapid` are two *separate* markets
  on `chess_moves` and are never pooled together.
- **Dota** rates on `dota2_gpm` (primary) + `dota2_kda_ratio` (secondary), and
  only **ranked** matchmaking counts (a gate the adapter must enforce).
- **PUBG** stays pooled across official BR modes on `pubg_damage` (primary) +
  `pubg_kills` (secondary).

The `mode` here is the *bucketing mode tag* (`competitive`, `blitz`, `rapid`,
`ranked`, `official`) — the granularity a market is cut and matched at — not the
raw host game mode. The adapter is responsible for only feeding matches whose
host mode maps to the market's `mode` (§ "Where in the code each rule lives").
"""

from __future__ import annotations

from dataclasses import dataclass

from ...constants import (
    GAME_CHESS_LICHESS,
    GAME_CS2_STEAM,
    GAME_DOTA2_OPENDOTA,
    GAME_PUBG_STEAM,
    lower_is_better,
    metric_floor,
)

# The two placement systems (Phase 4).
SYSTEM_HISTORY = "history"  # System 1 — backfillable history (chess, dota, pubg)
SYSTEM_NO_HISTORY = "no_history"  # System 2 — no fetchable history (cs2)


@dataclass(frozen=True)
class BucketMarket:
    """One bucketed market and everything the engine needs to run it."""

    game: str
    mode: str
    metric: str
    #: True when a smaller value is the better result (chess moves). Sourced from
    #: the existing `constants.lower_is_better` so there is one definition.
    lower_is_better: bool
    #: Smallest physically possible value (from `constants.metric_floor`).
    floor: float
    #: Placement system (which onboarding path this game uses).
    placement: str
    #: `True` for the game's primary (safe count/rate) metric; secondary metrics
    #: (heavy-tailed ratios) get more conservative bar placement.
    primary: bool
    #: History floor — matches needed before normal (uncapped) stakes. 0 for CS2.
    history_floor: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.game, self.mode, self.metric)

    @property
    def key_str(self) -> str:
        return f"{self.game}:{self.mode}:{self.metric}"


def _mk(game, mode, metric, placement, primary, history_floor) -> BucketMarket:
    return BucketMarket(
        game=game,
        mode=mode,
        metric=metric,
        lower_is_better=lower_is_better(metric),
        floor=metric_floor(metric),
        placement=placement,
        primary=primary,
        history_floor=history_floor,
    )


# The authoritative launch catalogue. `cs2_score` is intentionally absent until
# the CS2 adapter can distinguish Competitive from Premier/Wingman (see spec).
MARKETS: tuple[BucketMarket, ...] = (
    # CS2 — Competitive only, no fetchable history (System 2).
    _mk(GAME_CS2_STEAM, "competitive", "cs2_kills", SYSTEM_NO_HISTORY, True, 0),
    _mk(GAME_CS2_STEAM, "competitive", "cs2_kd_ratio", SYSTEM_NO_HISTORY, False, 0),
    # Chess — Blitz and Rapid as two independent markets (System 1).
    _mk(GAME_CHESS_LICHESS, "blitz", "chess_moves", SYSTEM_HISTORY, True, 20),
    _mk(GAME_CHESS_LICHESS, "rapid", "chess_moves", SYSTEM_HISTORY, True, 20),
    # Dota 2 — ranked matchmaking only (System 1).
    _mk(GAME_DOTA2_OPENDOTA, "ranked", "dota2_gpm", SYSTEM_HISTORY, True, 25),
    _mk(GAME_DOTA2_OPENDOTA, "ranked", "dota2_kda_ratio", SYSTEM_HISTORY, False, 25),
    # PUBG — official BR modes, pooled (System 1).
    _mk(GAME_PUBG_STEAM, "official", "pubg_damage", SYSTEM_HISTORY, True, 20),
    _mk(GAME_PUBG_STEAM, "official", "pubg_kills", SYSTEM_HISTORY, False, 20),
)

_BY_KEY: dict[tuple[str, str, str], BucketMarket] = {m.key: m for m in MARKETS}


def get(game: str, mode: str, metric: str) -> BucketMarket | None:
    return _BY_KEY.get((game, mode, metric))


def for_game(game: str) -> list[BucketMarket]:
    return [m for m in MARKETS if m.game == game]


def all_markets() -> tuple[BucketMarket, ...]:
    return MARKETS
