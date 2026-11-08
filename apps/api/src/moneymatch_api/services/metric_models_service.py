"""Metric-model bootstrap + refresh."""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..constants import (
    GAME_RATE_METRICS,
    METRIC_EWMA_HALF_LIFE,
    rated_only_game,
)
from ..models.skill import MetricModel

_BOOTSTRAP_MATCH_LIMIT = 50


async def get_metric_model(
    session: AsyncSession, user_id: uuid.UUID, game: str, metric: str
) -> MetricModel | None:
    """The user's model for one game+metric, or None if they have none yet."""
    return await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user_id,
            MetricModel.game == game,
            MetricModel.metric == metric,
        )
    )


def compute_ewma(
    values: list[float], half_life: int = METRIC_EWMA_HALF_LIFE
) -> tuple[float, float, int]:
    """Recency-weighted (mean, std-dev, n) over ``values`` (oldest-first)."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0
    weights = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
    total_w = sum(weights)
    mu = sum(w * x for w, x in zip(weights, values, strict=True)) / total_w
    var = sum(w * (x - mu) ** 2 for w, x in zip(weights, values, strict=True)) / total_w
    return mu, math.sqrt(var), n


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
    """Fetch recent history and (re)compute this account's metric models."""
    metrics = GAME_RATE_METRICS.get(game, ())
    if not metrics:
        return []

    adapter = registry.get(game)
    games: list[NormGame] = await adapter.poll_eligible_games(
        host_account_id,
        0,
        GameFilters(rated_only=rated_only_game(game)),
    )
    games = games[-_BOOTSTRAP_MATCH_LIMIT:]

    written: list[MetricModel] = []
    for metric in metrics:
        values = [g.metrics[metric] for g in games if metric in g.metrics]
        mu, sigma, n = compute_ewma(values)

        if n == 0:
            existing = await session.scalar(
                select(MetricModel).where(
                    MetricModel.user_id == user_id,
                    MetricModel.game == game,
                    MetricModel.metric == metric,
                )
            )
            if existing is not None:
                written.append(existing)
                continue

        written.append(await _upsert(session, user_id, game, metric, mu, sigma, n))
    return written
