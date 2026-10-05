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

import math
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..constants import (
    METRIC_BAR_INCREMENT,
    lower_is_better,
    metric_floor,
    requires_win,
)
from ..models.pools import SoloEntry, SoloPool
from ..services.hosts.errors import HostError
from . import demo_mode, raw_payload_service, test_opponents
from .pool_engine import PoolGrade

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


def _clearing_value(metric: str, bar: float) -> float:
    """A believable score for the opponent built to clear `bar`.

    Snapped up to the metric's own increment, because the number goes on the
    results card next to yours. Kills come in whole units, and an opponent
    credited with 18.4 kills reads as a bug in the thing holding your money.
    Rounding up rather than to nearest also keeps it strictly past the bar, so
    the score shown always agrees with the grade awarded.
    """
    increment = METRIC_BAR_INCREMENT.get(metric, 0.01)
    return round(math.ceil(bar * 1.15 / increment) * increment, 2)


async def grade_pool(
    session: AsyncSession, pool: SoloPool, entries: list[SoloEntry]
) -> dict[uuid.UUID, PoolGrade]:
    """Grade every entry's first qualifying in-window match against `room_bar`."""
    grades: dict[uuid.UUID, PoolGrade] = {}
    for entry in entries:
        # Practice opponents never play, so they are graded rather than looked
        # up. Most miss and forfeit their entry: without that they would grade
        # as unverifiable and be refunded, and a test pool would pay nobody.
        #
        # One is built to clear (`CLEARING_HANDLES`), because a pool where only
        # you can win never exercises the rule that decides the money — clearers
        # *split* the pot. With a clearing opponent in the room, clearing your
        # bar splits it and missing yours hands it over, which is the real
        # behaviour a single real player otherwise cannot reach.
        if test_opponents.is_practice_opponent(entry.host_account_id):
            cleared = test_opponents.clears_its_bar(entry.host_account_id)
            grades[entry.user_id] = PoolGrade(
                cleared=cleared,
                telemetry={
                    pool.metric: _clearing_value(pool.metric, float(pool.room_bar))
                    if cleared
                    else None,
                    "practice_opponent": True,
                },
            )
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
