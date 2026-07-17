"""Queue health for the admin surface (09-phase-6 · deliverable 2 · Queue).

Depth per (game, market, tier) among currently-waiting tickets, the mean wait of
those still waiting, and the lifetime expiry rate — all read straight off
`queue_tickets`, the queue-health source (01-architecture §2 · events)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.play import QueueTicket


@dataclass
class DepthRow:
    game: str
    market: str
    entry_cents: int
    waiting: int
    avg_wait_seconds: float


@dataclass
class QueueStats:
    waiting: int = 0
    matched: int = 0
    expired: int = 0
    canceled: int = 0
    expiry_rate: float = 0.0
    depth: list[DepthRow] = field(default_factory=list)


async def queue_stats(
    session: AsyncSession, *, now: datetime | None = None
) -> QueueStats:
    now = now or datetime.now(UTC)
    stats = QueueStats()

    # Global counts by state.
    by_state = await session.execute(
        select(QueueTicket.state, func.count()).group_by(QueueTicket.state)
    )
    counts = {state: int(n) for state, n in by_state}
    stats.waiting = counts.get("waiting", 0)
    stats.matched = counts.get("matched", 0)
    stats.expired = counts.get("expired", 0)
    stats.canceled = counts.get("canceled", 0)

    resolved = stats.matched + stats.expired
    stats.expiry_rate = (stats.expired / resolved) if resolved else 0.0

    # Depth + mean wait per (game, market, tier) among still-waiting tickets.
    rows = await session.execute(
        select(
            QueueTicket.game,
            QueueTicket.market,
            QueueTicket.entry_cents,
            func.count(),
            func.avg(func.extract("epoch", now - QueueTicket.created_at)),
        )
        .where(QueueTicket.state == "waiting")
        .group_by(QueueTicket.game, QueueTicket.market, QueueTicket.entry_cents)
        .order_by(QueueTicket.game, QueueTicket.market, QueueTicket.entry_cents)
    )
    for game, market, entry_cents, count, avg_wait in rows:
        stats.depth.append(
            DepthRow(
                game=game,
                market=market,
                entry_cents=entry_cents,
                waiting=int(count),
                avg_wait_seconds=float(avg_wait or 0.0),
            )
        )
    return stats
