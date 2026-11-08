from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    PAIR_RAKE_CONTESTS_PER_DAY,
    PAIR_RAKE_CONTESTS_PER_WEEK,
    WIN_STREAK_THRESHOLD,
)
from ..models.play import Match, MatchPlayer
from ..models.risk import RiskFlag
from ..services.match_states import CANCELED, SETTLED

log = structlog.get_logger(__name__)

WIN_STREAK_METRIC = "*"

PAIR_CAP_GAME = "*"
PAIR_CAP_METRIC = "*"


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
    `win_streak` flag.
    """
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


async def _pair_rake_count(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID, since: datetime
) -> int:
    """Rake-bearing (non-friendly, non-canceled) matches between two users since a
    cutoff.
    """
    p1 = MatchPlayer.__table__.alias("rp1")
    p2 = MatchPlayer.__table__.alias("rp2")
    stmt = (
        select(func.count())
        .select_from(
            Match.__table__.join(p1, p1.c.match_id == Match.id).join(
                p2, p2.c.match_id == Match.id
            )
        )
        .where(
            p1.c.user_id == a,
            p2.c.user_id == b,
            Match.friendly.is_(False),
            Match.state != CANCELED,
            Match.created_at >= since,
        )
    )
    return int(await session.scalar(stmt) or 0)


async def _has_open_pair_cap(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    existing = await session.scalar(
        select(RiskFlag.id).where(
            RiskFlag.user_id == a,
            RiskFlag.kind == "pair_cap",
            RiskFlag.resolved.is_(False),
            RiskFlag.detail["counterparty"].astext == str(b),
        )
    )
    return existing is not None


async def detect_pair_cap_breaches(
    session: AsyncSession, *, now: datetime | None = None
) -> int:
    """Flag pairs whose rake-bearing contest count strictly *exceeds* the pair cap in
    the daily or weekly window.
    """
    now = now or datetime.now(UTC)
    day_since = now - timedelta(days=1)
    week_since = now - timedelta(days=7)

    p1 = MatchPlayer.__table__.alias("pp1")
    p2 = MatchPlayer.__table__.alias("pp2")
    pairs = await session.execute(
        select(p1.c.user_id, p2.c.user_id)
        .select_from(
            Match.__table__.join(p1, p1.c.match_id == Match.id).join(
                p2, p2.c.match_id == Match.id
            )
        )
        .where(
            p1.c.user_id < p2.c.user_id,
            Match.friendly.is_(False),
            Match.state != CANCELED,
        )
        .distinct()
    )

    written = 0
    for a, b in pairs.all():
        if await _has_open_pair_cap(session, a, b):
            continue
        day = await _pair_rake_count(session, a, b, day_since)
        week = await _pair_rake_count(session, a, b, week_since)
        if day <= PAIR_RAKE_CONTESTS_PER_DAY and week <= PAIR_RAKE_CONTESTS_PER_WEEK:
            continue
        session.add(
            RiskFlag(
                user_id=a,
                game=PAIR_CAP_GAME,
                metric=PAIR_CAP_METRIC,
                kind="pair_cap",
                detail={
                    "counterparty": str(b),
                    "day_count": day,
                    "week_count": week,
                    "per_day_cap": PAIR_RAKE_CONTESTS_PER_DAY,
                    "per_week_cap": PAIR_RAKE_CONTESTS_PER_WEEK,
                },
            )
        )
        written += 1
        log.warning(
            "risk.pair_cap_flagged",
            user_id=str(a),
            counterparty=str(b),
            day_count=day,
            week_count=week,
        )

    await session.flush()
    return written
