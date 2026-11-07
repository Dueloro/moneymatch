"""Server-fetched telemetry grading for pools & tournaments."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..constants import (
    lower_is_better,
    metric_floor,
    rated_only_game,
    requires_win,
)
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..services.hosts.errors import HostError
from . import aggregate_metrics, raw_payload_service
from .pool_engine import PoolGrade
from .tournament_engine import TournamentGrade

log = structlog.get_logger(__name__)


async def _window_games(
    game: str, host_account_id: str, starts, ends, rated_only: bool = True
) -> list[NormGame] | None:
    """The entrant's finished matches inside `[starts, ends]`, oldest-first. `None`
    signals a host outage (adapter raised) — the caller refunds; an empty list
    means the account was readable but played nothing in the window.
    """
    starts_ms = int(starts.timestamp() * 1000)
    ends_ms = int(ends.timestamp() * 1000)
    adapter = registry.get(game)
    try:
        games = await adapter.poll_eligible_games(
            host_account_id, starts_ms, GameFilters(rated_only=rated_only)
        )
    except HostError:
        log.warning("telemetry.host_unavailable", game=game, host=host_account_id)
        return None
    return [g for g in games if starts_ms <= g.created_at_ms <= ends_ms]


def _evidence(
    entry_id: uuid.UUID, metric: str, games: list[NormGame]
) -> dict[str, Any]:
    return {
        "entry_id": str(entry_id),
        "metric": metric,
        "matches": [
            {
                "id": g.id,
                "created_at_ms": g.created_at_ms,
                "value": g.metrics.get(metric),
            }
            for g in games
        ],
    }


async def grade_pool(
    session: AsyncSession, pool: SoloPool, entries: list[SoloEntry]
) -> dict[uuid.UUID, PoolGrade]:
    """Grade every entry's first qualifying in-window match against `room_bar`."""
    grades: dict[uuid.UUID, PoolGrade] = {}
    for entry in entries:
        games = await _window_games(
            pool.game,
            entry.host_account_id,
            pool.window_starts_at,
            pool.window_ends_at,
            rated_only_game(pool.game),
        )
        if games is None or not games:
            grades[entry.user_id] = PoolGrade(cleared=None)  # unverifiable → refund
            continue

        floor = metric_floor(pool.metric)
        graded = next(
            (
                g
                for g in games
                if (v := g.metrics.get(pool.metric)) is not None and v >= floor
            ),
            games[0],
        )
        value = graded.metrics.get(pool.metric)
        if value is not None and value < floor:
            value = None
        payload = await raw_payload_service.persist(
            session,
            f"grade:{pool.game}",
            _evidence(entry.id, pool.metric, [graded]),
            memo=f"pool {pool.metric}",
        )
        if value is None:
            # Refunding here would turn entering and losing into a free option, and
            # would hand a loss the same outcome as never playing at all.
            grades[entry.user_id] = PoolGrade(
                cleared=False if requires_win(pool.metric) else None,
                telemetry={pool.metric: None, "won": graded.won},
                raw_payload_id=payload.id,
            )
            continue
        grades[entry.user_id] = PoolGrade(
            cleared=(
                value <= pool.room_bar
                if lower_is_better(pool.metric)
                else value >= pool.room_bar
            ),
            telemetry={pool.metric: value},
            raw_payload_id=payload.id,
        )
    return grades


async def grade_tournament(
    session: AsyncSession,
    tournament: Tournament,
    entries: list[TournamentEntry],
) -> dict[uuid.UUID, TournamentGrade]:
    """Score each entry's in-window aggregate result (keyed by entry id)."""
    metric = tournament.ranking_metric
    spec = aggregate_metrics.REGISTRY[metric]
    grades: dict[uuid.UUID, TournamentGrade] = {}
    for entry in entries:
        games = await _window_games(
            tournament.game,
            entry.host_account_id,
            tournament.window_starts_at,
            tournament.window_ends_at,
            rated_only_game(tournament.game),
        )
        if games is None:
            grades[entry.id] = TournamentGrade(values=None)  # host outage → refund
            continue
        score = spec.score(games)
        payload = await raw_payload_service.persist(
            session,
            f"grade:{tournament.game}",
            _evidence(entry.id, metric, games),
            memo=f"tournament {metric}",
        )
        grades[entry.id] = TournamentGrade(
            values=[] if score is None else [score],
            score=score,
            counted=spec.counted(games),
            telemetry={metric: score, "games": len(games)},
            raw_payload_id=payload.id,
        )
    return grades


async def live_standings(
    session: AsyncSession,
    tournament: Tournament,
    entries: list[TournamentEntry],
    usernames: dict[uuid.UUID, str | None],
) -> list[dict[str, Any]]:
    """Compute current standings mid-window (cheap host reads; cached by caller)."""
    metric = tournament.ranking_metric
    spec = aggregate_metrics.REGISTRY[metric]
    rows: list[dict[str, Any]] = []
    for entry in entries:
        games = await _window_games(
            tournament.game,
            entry.host_account_id,
            tournament.window_starts_at,
            tournament.window_ends_at,
            rated_only_game(tournament.game),
        )
        rows.append(
            {
                "user_id": str(entry.user_id),
                "username": usernames.get(entry.user_id),
                "score": spec.score(games or []),
                "matches": spec.counted(games or []),
            }
        )
    sign = 1.0 if aggregate_metrics.higher_is_better(metric) else -1.0
    rows.sort(key=lambda r: (r["score"] is None, -sign * (r["score"] or 0.0)))
    for i, row in enumerate(rows):
        row["rank"] = i + 1 if row["score"] is not None else None
    return rows
