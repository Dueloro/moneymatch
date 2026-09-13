"""Persistence + settlement hook for the win-streak matchmaking ladder (Phase 4).

Thin DB glue over the pure `streak_ladder` maths:

- `apply_result` — called when a 1v1 settles: win → streak+1, loss → 0, draw/void
  → unchanged. Tracks `best_streak` for display.
- `matchmaking_target_for` — the index a streaked player should be matched around,
  derived from their own bucketing index + the market's bucket width (rung size) +
  their current streak. Returns `None` when the player isn't placed yet.

Flush-not-commit; the caller owns the transaction (same posture as the rest).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player_streak import PlayerStreak
from . import streak_ladder as sl
from .bucketing import markets as mk
from .bucketing import state as bstate


async def get_streak(
    session: AsyncSession, player_id: uuid.UUID, game: str, mode: str
) -> int:
    row = await session.scalar(
        select(PlayerStreak.streak).where(
            PlayerStreak.player_id == player_id,
            PlayerStreak.game == game,
            PlayerStreak.mode == mode,
        )
    )
    return int(row or 0)


async def apply_result(
    session: AsyncSession,
    player_id: uuid.UUID,
    game: str,
    mode: str,
    won: bool | None,
) -> PlayerStreak:
    """Fold one settled 1v1 result into the player's streak. Idempotency is the
    caller's responsibility (call once per settled match, from the settlement
    transaction) — the streak is derived state, not a ledger."""
    row = await session.scalar(
        select(PlayerStreak).where(
            PlayerStreak.player_id == player_id,
            PlayerStreak.game == game,
            PlayerStreak.mode == mode,
        )
    )
    if row is None:
        row = PlayerStreak(
            player_id=player_id, game=game, mode=mode, streak=0, best_streak=0
        )
        session.add(row)

    row.streak = sl.streak_after(row.streak, won)
    if row.streak > row.best_streak:
        row.best_streak = row.streak
    await session.flush()
    return row


def _median_bucket_width(cuts: list[float]) -> float:
    """A representative bucket width (median gap between cut points) → rung size.
    Zero when the market has no interior cuts yet (single band)."""
    if len(cuts) < 2:
        return 0.0
    gaps = sorted(b - a for a, b in zip(cuts, cuts[1:], strict=False))
    return gaps[len(gaps) // 2]


async def matchmaking_target_for(
    session: AsyncSession,
    player_id: uuid.UUID,
    market: mk.BucketMarket,
) -> float | None:
    """The index this player should be matched *around*, after their win streak.

    `None` if they aren't placed in the market yet (no index to climb from).
    """
    ms = await bstate.get_market_state(
        session, player_id, market.game, market.mode, market.metric
    )
    if ms is None or ms.bucket is None:
        return None

    ref = await bstate.get_active_reference(
        session, market.game, market.mode, market.metric
    )
    width = _median_bucket_width(list(ref.cuts)) if ref is not None else 0.0
    rung = sl.rung_size_from_bucket_width(width)

    streak = await get_streak(session, player_id, market.game, market.mode)
    return sl.matchmaking_target(
        ms.index_value,
        streak,
        rung_size=rung,
        lower_is_better=market.lower_is_better,
    )
