"""Injecting a finished match, so a wager can settle without waiting on a host.

**Scaffolding. Delete with the rest of the demo surface before launch.**

The rule this module exists to respect: a simulated result must enter the system
at the *same seam* a real one does, and nothing downstream may know the
difference. Grading, pools, tournaments and the live activity ticker all reach a
game host through one call, `adapters.registry.get(game).poll_eligible_games()`.
So that is where an injected match is merged in, and nowhere else. There is no
`if simulated` branch in the settlement worker, the engines, or the payout path,
because the moment there is one, a green demo stops being evidence that the real
path works.

Gated twice: `DEMO_SIMULATE_ENABLED` must be set, and the endpoint that writes
these rows is admin-only. With the flag off, `registry.get()` returns the
untouched host adapter and these rows are never read.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.base import NormGame
from ..config import get_settings
from ..models.demo_simulation import SimulatedMatch

log = structlog.get_logger(__name__)


def is_enabled() -> bool:
    """Whether injected results are readable at all."""
    return bool(get_settings().demo_simulate_enabled)


async def record(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    game: str,
    host_account_id: str,
    metrics: dict[str, float],
    won: bool | None,
    drawn: bool = False,
    rounds: int = 0,
    moves: int = 0,
    played_at: datetime | None = None,
    created_by: str,
) -> SimulatedMatch:
    """Persist one injected finished match."""
    when = played_at or datetime.now(UTC)
    row = SimulatedMatch(
        user_id=user_id,
        game=game,
        host_account_id=host_account_id,
        created_at_ms=int(when.timestamp() * 1000),
        won=won,
        drawn=drawn,
        rounds=rounds,
        moves=moves,
        metrics={k: float(v) for k, v in (metrics or {}).items()},
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    # Loud on purpose. A simulated settlement must be identifiable in the logs
    # after the fact, because it is indistinguishable everywhere else.
    log.warning(
        "demo.simulated_match_injected",
        simulated=True,
        match_id=str(row.id),
        user_id=str(user_id),
        game=game,
        host_account_id=host_account_id,
        metrics=row.metrics,
        won=won,
        rounds=rounds,
        created_by=created_by,
    )
    return row


def _to_norm(row: SimulatedMatch, speed: str) -> NormGame:
    return NormGame(
        id=f"sim-{row.id}",
        speed=speed,
        rated=True,
        created_at_ms=int(row.created_at_ms),
        moves=int(row.moves),
        won=row.won,
        drawn=bool(row.drawn),
        metrics={k: float(v) for k, v in (row.metrics or {}).items()},
    )


async def games_for(
    game: str, host_account_id: str, since_ms: int, speed: str
) -> list[NormGame]:
    """Injected matches for one host account, oldest first.

    Opens its own session: this is called from inside an adapter, which has no
    request scope and runs in both the API and the worker process.
    """
    if not is_enabled():
        return []

    from ..db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = list(
            await session.scalars(
                select(SimulatedMatch)
                .where(
                    SimulatedMatch.game == game,
                    SimulatedMatch.host_account_id == host_account_id,
                    SimulatedMatch.created_at_ms >= since_ms,
                )
                .order_by(SimulatedMatch.created_at_ms)
            )
        )
    return [_to_norm(r, speed) for r in rows]


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 25
) -> list[dict[str, Any]]:
    """Recent injected matches for a user, for the admin view."""
    rows = list(
        await session.scalars(
            select(SimulatedMatch)
            .where(SimulatedMatch.user_id == user_id)
            .order_by(SimulatedMatch.created_at_ms.desc())
            .limit(limit)
        )
    )
    return [
        {
            "id": str(r.id),
            "game": r.game,
            "host_account_id": r.host_account_id,
            "created_at_ms": int(r.created_at_ms),
            "won": r.won,
            "rounds": int(r.rounds),
            "metrics": r.metrics,
            "created_by": r.created_by,
            "simulated": True,
        }
        for r in rows
    ]


__all__ = ["games_for", "is_enabled", "list_for_user", "record"]
