"""Sandbagging detector v1 (07-phase-4 · deliverable 10).

The personal-bar feature makes **tanking your own baseline** the attack that pays:
a low frozen μ gives you a trivially clearable bar. So this ships *with* the
feature. When a player's recent-form mean sits a z-score below their own older
baseline, we write a `risk_flags` row and block metric wagers on that game/metric
until an admin clears it (the review queue lands in Phase 6).

The z-test is pure and unit-tested; the live evaluation fetches the account's
recent history through the adapter. A host outage during evaluation **fails
open** (skip detection, never block a legitimate player on infra) — persisted
flags still block.
"""

from __future__ import annotations

import math
import statistics
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..adapters.base import GameFilters
from ..constants import SANDBAG_RECENT_N, SANDBAG_Z_THRESHOLD
from ..errors import APIError
from ..models.risk import RiskFlag
from ..models.user import User
from ..services.hosts.errors import HostError

log = structlog.get_logger(__name__)

# Need at least this many older matches beyond the recent window to form a baseline.
_MIN_BASELINE = 5


class SandbaggingBlockedError(APIError):
    """A metric wager is blocked by an open sandbagging flag (409)."""

    def __init__(self, game: str, metric: str) -> None:
        super().__init__(
            "sandbagging_flagged",
            "Your recent form on this stat dropped sharply — metric wagers are "
            "paused for review. This protects the personalized-bar fairness.",
            status_code=409,
            detail={"game": game, "metric": metric},
        )


def sandbag_z(
    values_newest_first: list[float], recent_n: int = SANDBAG_RECENT_N
) -> float | None:
    """z-score of the recent-N mean vs. the older baseline. Below the threshold ⇒
    suspicious tanking. `None` when there isn't enough history to judge."""
    if len(values_newest_first) < recent_n + _MIN_BASELINE:
        return None
    recent = values_newest_first[:recent_n]
    baseline = values_newest_first[recent_n:]
    bmean = statistics.fmean(baseline)
    bstd = statistics.pstdev(baseline)
    if bstd <= 0:
        return None
    rmean = statistics.fmean(recent)
    return (rmean - bmean) / (bstd / math.sqrt(len(recent)))


async def is_flagged(
    session: AsyncSession, user_id: uuid.UUID, game: str, metric: str
) -> bool:
    """Whether an unresolved sandbagging flag exists for this user/game/metric."""
    flag = await session.scalar(
        select(RiskFlag).where(
            RiskFlag.user_id == user_id,
            RiskFlag.game == game,
            RiskFlag.metric == metric,
            RiskFlag.resolved.is_(False),
        )
    )
    return flag is not None


async def evaluate(
    session: AsyncSession, user: User, game: str, metric: str, host_account_id: str
) -> RiskFlag | None:
    """Run the detector against live history; write + return a flag if tanking."""
    adapter = registry.get(game)
    try:
        games = await adapter.poll_eligible_games(host_account_id, 0, GameFilters())
    except HostError:
        return None  # fail open — never block on a host outage
    # Adapters return oldest-first; reverse for newest-first.
    values = [g.metrics[metric] for g in reversed(games) if metric in g.metrics]
    z = sandbag_z(values, SANDBAG_RECENT_N)
    if z is None or z >= SANDBAG_Z_THRESHOLD:
        return None
    flag = RiskFlag(
        user_id=user.id,
        game=game,
        metric=metric,
        kind="sandbagging",
        detail={"z": round(z, 3), "recent_n": SANDBAG_RECENT_N},
    )
    session.add(flag)
    await session.flush()
    log.warning(
        "sandbagging.flagged",
        user_id=str(user.id),
        game=game,
        metric=metric,
        z=round(z, 3),
    )
    return flag


async def assert_not_sandbagging(
    session: AsyncSession, user: User, game: str, metric: str, host_account_id: str
) -> None:
    """Block a metric wager on an existing flag, or on a fresh detection."""
    if await is_flagged(session, user.id, game, metric):
        raise SandbaggingBlockedError(game, metric)
    if await evaluate(session, user, game, metric, host_account_id) is not None:
        raise SandbaggingBlockedError(game, metric)
