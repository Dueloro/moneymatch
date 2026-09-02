"""Phase 1 — idempotent ingestion (record every match once, store everything).

`record_match` is the single entry point the worker calls for each finished,
gradable match a linked player produces. It writes one append-only `match_stats`
row, keyed so that re-ingesting the same match (the poller *will* re-see it) is a
concurrency-safe no-op.

Two decisions worth calling out:

1. **Store more than we rate on.** The `metrics` dict is written verbatim — every
   field the adapter exposed, not just the rated subset — because storing a field
   is free and future-proof (the ML corpus) while not storing it is unrecoverable.
   `record_match` never filters `metrics`.

2. **The mode gate is fail-closed.** `bucket_mode_for` maps a match to the
   bucketing *mode tag* for its market, or returns `None` to skip it. It only
   returns a mode when the game's mode discriminator actually exists:
   - **chess** — `blitz` / `rapid` only (from `NormGame.speed`); bullet/classical
     and variants are skipped. Ready today.
   - **PUBG** — the official BR modes, pooled under `official`. Ready today.
   - **CS2** — needs Competitive-vs-Premier/Wingman discrimination that the GC
     resolve payload does not yet surface (spec gap). Returns `None` until the
     adapter can tell them apart, so we never record a CS2 match into a market we
     can't correctly gate.
   - **Dota** — needs a `lobby_type == ranked` gate the adapter does not yet
     enforce (spec gap). Returns `None` until that lands.

   This is deliberate: enabling CS2/Dota bucketing is a two-step change — close
   the discriminator gap in the adapter, then turn the mode on here — and until
   then the fail-closed default keeps ungated data out of the money path.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...adapters.base import NormGame
from ...constants import (
    GAME_CHESS_LICHESS,
    GAME_CS2_STEAM,
    GAME_DOTA2_OPENDOTA,
    GAME_PUBG_STEAM,
    PUBG_OFFICIAL_GAME_MODES,
)
from ...models.bucketing import MatchStat

# Chess speeds that get a bucketing market (each is its own market).
_CHESS_BUCKET_SPEEDS = frozenset({"blitz", "rapid"})

# Per-game readiness of the mode discriminator. False → we do not yet record any
# match for that game (fail-closed). Flip to True only once the adapter can gate
# the mode correctly (see module docstring).
MODE_GATE_READY: dict[str, bool] = {
    GAME_CHESS_LICHESS: True,
    GAME_PUBG_STEAM: True,
    GAME_CS2_STEAM: False,  # needs Competitive discriminator
    GAME_DOTA2_OPENDOTA: False,  # needs ranked (lobby_type) gate
}


def bucket_mode_for(game: str, norm: NormGame) -> str | None:
    """The bucketing mode tag for a normalized match, or `None` to skip it.

    Fail-closed: an unknown game, a not-ready discriminator, or a mode outside the
    launch scope all return `None`.
    """
    if not MODE_GATE_READY.get(game, False):
        return None

    if game == GAME_CHESS_LICHESS:
        return norm.speed if norm.speed in _CHESS_BUCKET_SPEEDS else None

    if game == GAME_PUBG_STEAM:
        # `NormGame.speed` carries the PUBG gameMode; the adapter already dropped
        # custom/event, but re-check the official set here so ingestion is
        # self-defending rather than trusting an upstream filter.
        return "official" if norm.speed in PUBG_OFFICIAL_GAME_MODES else None

    # CS2 and Dota are gated off above until their discriminators land.
    return None


async def record_match(
    session: AsyncSession,
    player_id: uuid.UUID,
    game: str,
    norm: NormGame,
    *,
    mode: str | None = None,
) -> bool:
    """Record one finished match idempotently. Returns True iff a new row was
    written (False when it was already recorded — the safe re-ingest path).

    - `mode` may be supplied by the caller; otherwise it's derived via
      `bucket_mode_for`. A `None` mode (match not in scope) records nothing and
      returns False.
    - Concurrency-safe: uses `INSERT … ON CONFLICT DO NOTHING` on the idempotency
      key, never a read-then-write (two workers can read "absent" at once).
    - Stores `norm.metrics` verbatim (every field the adapter exposed).
    """
    resolved_mode = mode if mode is not None else bucket_mode_for(game, norm)
    if resolved_mode is None:
        return False
    if not norm.id:
        return False

    stmt = (
        pg_insert(MatchStat)
        .values(
            player_id=player_id,
            game=game,
            mode=resolved_mode,
            host_match_id=norm.id,
            created_at_ms=norm.created_at_ms,
            won=norm.won,
            metrics=dict(norm.metrics),
        )
        .on_conflict_do_nothing(constraint="uq_match_stats_idem")
    )
    result = await session.execute(stmt)
    await session.flush()
    # rowcount is 1 on insert, 0 when the conflict skipped it.
    return bool(result.rowcount and result.rowcount > 0)
