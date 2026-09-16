"""Confidence-gated stake ceilings — the smurf defense / fish protection (Phase 4).

A new or low-confidence account may only stake small amounts; the cap opens as the
account builds a real record. This bounds how much a strong player on a fresh
account (a smurf) can take before the streak ladder pulls them up and out of the
beginner pool. The cap is driven by **how much record backs the account for that
game/market** (metric-model sample size for stat duels, host game count for chess),
not by raw wins — so it can't be farmed.

Pure math + a thin DB read; enforced at 1v1 and tournament entry.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import ENTRY_PRESETS_CENTS, METRIC_PROVISIONAL_MIN_N
from ..models.linked_account import LinkedAccount
from ..models.skill import MetricModel

# The cap gates only a genuinely new / low-record account. Below the sample floor
# (provisional) the account is held to the floor stake; once it has a real record
# it is uncapped (the full preset ladder). This bounds smurf extraction — a fresh
# account can only take small stakes until it has built a record, by which time
# the streak ladder has pulled a strong player up out of the beginner pool — while
# never penalising an established player.
_FLOOR = ENTRY_PRESETS_CENTS[0]


def ceiling_for_samples(n: int) -> int:
    """The max entry (cents) an account with `n` graded games may stake: the floor
    while provisional (n < the sample floor), the full ladder once established."""
    if n < METRIC_PROVISIONAL_MIN_N:
        return ENTRY_PRESETS_CENTS[0]
    return ENTRY_PRESETS_CENTS[-1]


async def _stat_samples(
    session: AsyncSession, user_id: uuid.UUID, game: str, metric: str
) -> int:
    model = await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user_id,
            MetricModel.game == game,
            MetricModel.metric == metric,
        )
    )
    return int(model.n) if model is not None else 0


def _host_games(link: LinkedAccount | None) -> int:
    """Total games the host reports for a chess-style account (from the snapshot)."""
    if link is None:
        return 0
    snap = link.profile_snapshot or {}
    total = snap.get("total_games")
    if isinstance(total, (int, float)):
        return int(total)
    return 0


async def ceiling_cents(
    session: AsyncSession,
    user_id: uuid.UUID,
    game: str,
    *,
    metric: str | None,
    link: LinkedAccount | None,
) -> int:
    """The stake ceiling for this account on this game/market. Stat duels use the
    metric-model sample size; win-only (chess) uses the host game count."""
    if metric is not None:
        n = await _stat_samples(session, user_id, game, metric)
    else:
        n = _host_games(link)
    return ceiling_for_samples(n)


def floor_cents() -> int:
    return _FLOOR
