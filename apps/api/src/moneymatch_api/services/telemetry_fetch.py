"""Server-fetched telemetry grading for pools & tournaments (07-phase-4 · 5).

At window end the worker asks each entrant's adapter for the matches they played
**inside the window** (`poll_eligible_games` bounded to `[window_starts,
window_ends]`), persists the normalized evidence to `raw_payloads`, and turns it
into a grade. Zero self-report anywhere — the player supplies nothing.

Watchdog rules (architecture §3.4):
- a host outage (adapter raises) → the entry is **unverifiable** → refunded
  (never a loss on infra);
- a pool entrant with no qualifying match → unverifiable → refunded;
- a tournament entrant with a readable history but no in-window match → an empty
  score list → **forfeit** (ranked last, paid nothing).

Window-boundary matches are excluded (strict `[starts, ends]` containment).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..services.hosts.errors import HostError
from . import raw_payload_service
from .pool_engine import PoolGrade
from .tournament_engine import TournamentGrade

log = structlog.get_logger(__name__)


async def _window_games(
    game: str, host_account_id: str, starts, ends
) -> list[NormGame] | None:
    """The entrant's finished matches inside `[starts, ends]`, oldest-first.

    `None` signals a host outage (adapter raised) — the caller refunds; an empty
    list means the account was readable but played nothing in the window.
    """
    starts_ms = int(starts.timestamp() * 1000)
    ends_ms = int(ends.timestamp() * 1000)
    adapter = registry.get(game)
    try:
        games = await adapter.poll_eligible_games(
            host_account_id, starts_ms, GameFilters(rated_only=False)
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
    """Grade every entry's first in-window match against `room_bar`."""
    grades: dict[uuid.UUID, PoolGrade] = {}
    for entry in entries:
        games = await _window_games(
            pool.game, entry.host_account_id, pool.window_starts_at, pool.window_ends_at
        )
        if games is None or not games or pool.metric not in games[0].metrics:
            grades[entry.user_id] = PoolGrade(cleared=None)  # unverifiable → refund
            continue
        value = games[0].metrics[pool.metric]
        payload = await raw_payload_service.persist(
            session,
            f"grade:{pool.game}",
            _evidence(entry.id, pool.metric, games[:1]),
            memo=f"pool {pool.metric}",
        )
        grades[entry.user_id] = PoolGrade(
            cleared=value >= pool.room_bar,
            telemetry={pool.metric: value},
            raw_payload_id=payload.id,
        )
    return grades


async def grade_tournament(
    session: AsyncSession,
    tournament: Tournament,
    entries: list[TournamentEntry],
) -> dict[uuid.UUID, TournamentGrade]:
    """Build each entry's first-N in-window metric values (keyed by entry id)."""
    metric = tournament.ranking_metric
    n = tournament.score_matches
    grades: dict[uuid.UUID, TournamentGrade] = {}
    for entry in entries:
        games = await _window_games(
            tournament.game,
            entry.host_account_id,
            tournament.window_starts_at,
            tournament.window_ends_at,
        )
        if games is None:
            grades[entry.id] = TournamentGrade(values=None)  # host outage → refund
            continue
        scored = [g for g in games if metric in g.metrics][:n]
        values = [g.metrics[metric] for g in scored]
        payload = await raw_payload_service.persist(
            session,
            f"grade:{tournament.game}",
            _evidence(entry.id, metric, scored),
            memo=f"tournament {metric}",
        )
        grades[entry.id] = TournamentGrade(
            values=values,  # [] ⇒ forfeit; non-empty ⇒ scored
            telemetry={metric: values},
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
    n = tournament.score_matches
    from . import fairness

    rows: list[dict[str, Any]] = []
    for entry in entries:
        games = await _window_games(
            tournament.game,
            entry.host_account_id,
            tournament.window_starts_at,
            tournament.window_ends_at,
        )
        values = (
            [g.metrics[metric] for g in games if metric in g.metrics][:n]
            if games
            else []
        )
        avg, count = fairness.first_n_average(values, n)
        rows.append(
            {
                "user_id": str(entry.user_id),
                "username": usernames.get(entry.user_id),
                "score": avg,
                "matches": count,
            }
        )
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0.0)))
    for i, row in enumerate(rows):
        row["rank"] = i + 1 if row["score"] is not None else None
    return rows
