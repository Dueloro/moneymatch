"""Metric-model bootstrap + refresh (05-phase-2 · deliverable 6).

On link (and later on settlement / nightly) we pull the account's recent finished
matches through its adapter and compute, per typed rate metric, a recency-weighted
EWMA mean/std-dev and sample size `n` (half-life 10). `n` below the config floor
marks the metric **provisional** (no stat duels/pools on it). Metrics are
rate-based only — the adapters never surface raw totals.

Pure math (`compute_ewma`) is separated from I/O so it is trivially testable.
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..constants import (
    GAME_HISTORY_FLOOR,
    GAME_RATE_METRICS,
    METRIC_EWMA_HALF_LIFE,
    METRIC_PROVISIONAL_MIN_N,
)
from ..models.skill import MetricModel

# How far back to pull for the bootstrap (~last N finished matches; adapters cap
# their own page sizes below this).
_BOOTSTRAP_MATCH_LIMIT = 50


def compute_ewma(
    values: list[float], half_life: int = METRIC_EWMA_HALF_LIFE
) -> tuple[float, float, int]:
    """Recency-weighted (mean, std-dev, n) over ``values`` (oldest-first).

    The most recent sample carries weight 1; each step older is halved every
    ``half_life`` samples. `n` is the raw sample count (drives provisional-ness).
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0
    weights = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
    total_w = sum(weights)
    mu = sum(w * x for w, x in zip(weights, values, strict=True)) / total_w
    var = sum(w * (x - mu) ** 2 for w, x in zip(weights, values, strict=True)) / total_w
    return mu, math.sqrt(var), n


def is_provisional(model: MetricModel) -> bool:
    """A metric with too few samples can't back a stat duel/pool."""
    return model.n < METRIC_PROVISIONAL_MIN_N


def meets_history_floor(game: str, total_finished: int) -> bool:
    """Whether an account clears the per-game history floor (else win-only)."""
    return total_finished >= GAME_HISTORY_FLOOR.get(game, 0)


async def _upsert(
    session: AsyncSession,
    user_id: uuid.UUID,
    game: str,
    metric: str,
    mu: float,
    sigma: float,
    n: int,
) -> MetricModel:
    existing = await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user_id,
            MetricModel.game == game,
            MetricModel.metric == metric,
        )
    )
    if existing is None:
        existing = MetricModel(user_id=user_id, game=game, metric=metric)
        session.add(existing)
    existing.mu = mu
    existing.sigma = sigma
    existing.n = n
    await session.flush()
    return existing


async def bootstrap(
    session: AsyncSession,
    user_id: uuid.UUID,
    game: str,
    host_account_id: str,
) -> list[MetricModel]:
    """Fetch recent history and (re)compute this account's metric models.

    Returns the models written (empty for win-only games like chess, or when the
    account has no readable rate metrics yet).
    """
    metrics = GAME_RATE_METRICS.get(game, ())
    if not metrics:
        return []

    adapter = registry.get(game)
    games: list[NormGame] = await adapter.poll_eligible_games(
        host_account_id, 0, GameFilters()
    )
    games = games[-_BOOTSTRAP_MATCH_LIMIT:]

    written: list[MetricModel] = []
    for metric in metrics:
        values = [g.metrics[metric] for g in games if metric in g.metrics]
        mu, sigma, n = compute_ewma(values)
        written.append(await _upsert(session, user_id, game, metric, mu, sigma, n))
    return written
