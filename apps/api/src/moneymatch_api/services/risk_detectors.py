"""Derived risk detectors (nightly) — backlog · Phase 6 "derived risk detectors".

The sandbagging detector writes flags on the wager hot path; the detectors here
run in the worker's nightly pass over *settled* history and write **informational**
`win_streak` risk flags (surfaced in the admin risk queue, never blocking play).
Kept pure of host calls — they read only our own `matches`, so they are cheap and
deterministic. `pair-cap` breaches are the natural next detector to add here.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import WIN_STREAK_THRESHOLD
from ..models.play import Match, MatchPlayer
from ..models.risk import RiskFlag
from ..services.match_states import SETTLED

log = structlog.get_logger(__name__)

# `win_streak` is a game-wide signal, not a per-metric duel; a sentinel metric
# keeps the non-null column satisfied without colliding with a real metric.
WIN_STREAK_METRIC = "*"


async def _has_open_win_streak(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> bool:
    existing = await session.scalar(
        select(RiskFlag.id).where(
            RiskFlag.user_id == user_id,
            RiskFlag.game == game,
            RiskFlag.kind == "win_streak",
            RiskFlag.resolved.is_(False),
        )
    )
    return existing is not None


async def detect_win_streaks(session: AsyncSession) -> int:
    """Flag each (user, game) on an unbroken run of >= ``WIN_STREAK_THRESHOLD``
    settled H2H wins. Idempotent: skips a pair that already has an open
    `win_streak` flag. Returns the count of new flags written."""
    pairs = await session.execute(
        select(MatchPlayer.user_id, Match.game)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.state == SETTLED)
        .distinct()
    )

    written = 0
    for user_id, game in pairs.all():
        if await _has_open_win_streak(session, user_id, game):
            continue
        recent = list(
            await session.scalars(
                select(Match.winner_user_id)
                .join(MatchPlayer, MatchPlayer.match_id == Match.id)
                .where(
                    MatchPlayer.user_id == user_id,
                    Match.game == game,
                    Match.state == SETTLED,
                )
                .order_by(Match.resolved_at.desc())
                .limit(WIN_STREAK_THRESHOLD)
            )
        )
        # Need a full window and every one of them won by this user.
        if len(recent) < WIN_STREAK_THRESHOLD or any(w != user_id for w in recent):
            continue
        session.add(
            RiskFlag(
                user_id=user_id,
                game=game,
                metric=WIN_STREAK_METRIC,
                kind="win_streak",
                detail={"streak": len(recent)},
            )
        )
        written += 1
        log.warning(
            "risk.win_streak_flagged",
            user_id=str(user_id),
            game=game,
            streak=len(recent),
        )

    await session.flush()
    return written
