"""Per-game player stats derived from settled contests. Only decided (SETTLED)
matches count — PUSHED / CANCELED contests are ignored, so a refund neither
extends nor breaks a streak.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.play import Match, MatchPlayer
from ..services.match_states import SETTLED


async def current_win_streaks(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[str, int]:
    """Map each game to the player's current win streak (0 when none)."""
    rows = await session.execute(
        select(Match.game, Match.winner_user_id)
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user_id, Match.state == SETTLED)
        .order_by(Match.resolved_at.desc().nullslast())
    )

    streaks: dict[str, int] = {}
    broken: set[str] = set()
    for game, winner_user_id in rows:
        if game in broken:
            continue
        if winner_user_id == user_id:
            streaks[game] = streaks.get(game, 0) + 1
        else:
            streaks.setdefault(game, 0)
            broken.add(game)
    return streaks
