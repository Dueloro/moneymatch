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
from ..constants import lower_is_better, metric_floor, requires_win
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..services.hosts.errors import HostError
from . import aggregate_metrics, demo_mode, raw_payload_service, test_opponents
from .pool_engine import PoolGrade
from .tournament_engine import TournamentGrade

log = structlog.get_logger(__name__)


async def _window_games(
    game: str, host_account_id: str, starts, ends, rated_only: bool = True
) -> list[NormGame] | None:
    """The entrant's finished matches inside `[starts, ends]`, oldest-first.

    `None` signals a host outage (adapter raised) — the caller refunds; an empty
    list means the account was readable but played nothing in the window.
    """
    starts_ms = int(starts.timestamp() * 1000)
    ends_ms = int(ends.timestamp() * 1000)
    adapter = registry.get(game)
    try:
        # Rated only for real accounts: a casual game must never move a pool bar
        # or a tournament score, and on Lichess a brokered duel is itself
        # casual, so this also stops a money duel feeding the stats it was
        # quoted from. The demo account opts in to casual games (demo_mode).
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
        # Practice opponents never play, so they miss the bar and forfeit their
        # entry. Without this they would grade as unverifiable and be refunded,
        # which would make a test pool pay nothing to anyone.
        if test_opponents.graded_as_failed(entry.host_account_id):
            grades[entry.user_id] = PoolGrade(cleared=False)
            continue
        games = await _window_games(
            pool.game,
            entry.host_account_id,
            pool.window_starts_at,
            pool.window_ends_at,
            await demo_mode.rated_only_for(session, entry.user_id, pool.game),
        )
        if games is None or not games:
            grades[entry.user_id] = PoolGrade(cleared=None)  # unverifiable → refund
            continue

        # The first match that produces a value is the graded attempt, not the
        # first match played: for a win-required metric a loss carries no value,
        # so grading `games[0]` would let one early loss forfeit a later win
        # that clears the bar. Taking the *first* qualifying game (not the best)
        # keeps it a single priced attempt, so the advertised clear rate holds.
        # A value below the metric floor is physically impossible and dropped as
        # bad evidence rather than allowed to clear beneath the floor.
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
            # No value on a match that was actually played. For a win-required
            # metric that means no win in the window, which is a definite
            # **miss**: they had their attempts and did not make it.
            # Refunding here would turn entering and losing into a free option,
            # and would hand a loss the same outcome as never playing at all.
            # Any other metric keeps the old reading: we could not measure it,
            # so we cannot claim they failed.
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
    """Build each entry's first-N in-window metric values (keyed by entry id)."""
    metric = tournament.ranking_metric
    n = tournament.score_matches
    grades: dict[uuid.UUID, TournamentGrade] = {}
    for entry in entries:
        # A practice opponent has no real host account, so ask its adapter
        # nothing: the username does not resolve and the call is wasted. It
        # posts a deliberately losing score instead of no score at all, because
        # `compute_standings` drops an unscored entry and a field of one
        # cancels the whole contest (see `test_opponents.practice_score`).
        if test_opponents.graded_as_failed(entry.host_account_id):
            score = test_opponents.practice_score(metric)
            grades[entry.id] = TournamentGrade(
                values=[] if score is None else [score],
                score=score,
                counted=0,
                telemetry={metric: score, "practice_opponent": True},
            )
            continue
        games = await _window_games(
            tournament.game,
            entry.host_account_id,
            tournament.window_starts_at,
            tournament.window_ends_at,
            await demo_mode.rated_only_for(session, entry.user_id, tournament.game),
        )
        if games is None:
            grades[entry.id] = TournamentGrade(values=None)  # host outage → refund
            continue
        spec = aggregate_metrics.get(metric)
        if spec is not None:
            # Scored over the whole window rather than a first-N mean: total
            # wins, longest streak, fastest win. `None` ⇒ no qualifying result,
            # which the engine already treats as a forfeit.
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
            await demo_mode.rated_only_for(session, entry.user_id, tournament.game),
        )
        spec = aggregate_metrics.get(metric)
        if spec is not None:
            avg = spec.score(games or [])
            count = spec.counted(games or [])
        else:
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
    # Fastest-win ranks smallest-first; everything else biggest-first.
    sign = 1.0 if aggregate_metrics.higher_is_better(metric) else -1.0
    rows.sort(key=lambda r: (r["score"] is None, -sign * (r["score"] or 0.0)))
    for i, row in enumerate(rows):
        row["rank"] = i + 1 if row["score"] is not None else None
    return rows
