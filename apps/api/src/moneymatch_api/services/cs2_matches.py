"""Storing resolved CS2 matches, and turning a scoreboard into metrics.

The settlement path never talks to the Game Coordinator. A share code is
resolved once, the scoreboard is stored, and grading reads the stored row. That
keeps a stateful, rate-limited Steam service off the critical path: if the
sidecar is down, wagers whose matches are already resolved still settle.

Three metrics come straight off the scoreboard, and one deliberately does not:

    cs2_kd_ratio      kills / deaths
    cs2_headshot_pct  headshots / kills * 100
    cs2_kills         kills
    cs2_adr           NOT here, it needs a parsed demo

A player with zero deaths is a real scoreline, so K/D falls back to the kill
count rather than dividing by zero. Zero kills means a headshot percentage of
zero, not an error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.cs2 import Cs2Match
from . import sharecode as sharecode_service

log = structlog.get_logger(__name__)


def metrics_from_line(line: dict[str, Any]) -> dict[str, float]:
    """The wagerable metrics for one player's scoreboard line."""
    kills = float(line.get("kills") or 0)
    deaths = float(line.get("deaths") or 0)
    headshots = float(line.get("headshots") or 0)
    return {
        # No deaths is a real result, not a divide by zero: the K/D of a
        # flawless game is its kill count.
        "cs2_kd_ratio": kills / deaths if deaths > 0 else kills,
        "cs2_headshot_pct": (headshots / kills * 100.0) if kills > 0 else 0.0,
        "cs2_kills": kills,
    }


async def get_by_share_code(session: AsyncSession, code: str) -> Cs2Match | None:
    return await session.scalar(
        select(Cs2Match).where(Cs2Match.share_code == sharecode_service.normalize(code))
    )


async def store(
    session: AsyncSession,
    *,
    code: str,
    resolved: dict[str, Any],
    submitted_by_user_id: uuid.UUID | None,
) -> Cs2Match:
    """Persist one resolved match. Idempotent on the share code.

    Two players in the same match pasting the same code is the same match, so
    the second submission returns the existing row rather than failing.
    """
    decoded = sharecode_service.decode(code)
    existing = await get_by_share_code(session, decoded.code)
    if existing is not None:
        return existing

    scores = resolved.get("scores") or {}
    players = resolved.get("players") or []
    match_time = resolved.get("matchTime")
    when = (
        datetime.fromtimestamp(int(match_time), UTC)
        if match_time is not None
        else datetime.now(UTC)
    )
    demo_url = resolved.get("demoUrl") or None

    row = Cs2Match(
        share_code=decoded.code,
        match_id=decoded.match_id,
        outcome_id=decoded.outcome_id,
        token_id=decoded.token_id,
        match_time=when,
        map_name=resolved.get("map"),
        rounds_total=int(scores.get("a", 0)) + int(scores.get("b", 0)),
        score_a=int(scores.get("a", 0)),
        score_b=int(scores.get("b", 0)),
        players=players,
        demo_url=demo_url,
        # Valve keeps demos about a month. Absent is normal and does not block
        # settlement; only the parse-only metrics are lost with it.
        demo_expired=bool(resolved.get("expired") or not demo_url),
        submitted_by_user_id=submitted_by_user_id,
        raw=resolved,
    )
    session.add(row)
    await session.flush()
    log.info(
        "cs2.match_stored",
        share_code=decoded.code,
        match_id=decoded.match_id,
        rounds=row.rounds_total,
        players=len(players),
        demo_expired=row.demo_expired,
    )
    return row


async def matches_for_steam_id(
    session: AsyncSession, steam_id: str, since: datetime | None = None
) -> list[Cs2Match]:
    """Stored matches whose roster contains `steam_id`, oldest first.

    The roster is filtered in Python rather than in SQL because it lives in a
    JSONB array and the row count is small, one per pasted code. If this grows,
    a GIN index and a containment query is the fix.
    """
    stmt = select(Cs2Match).order_by(Cs2Match.match_time)
    if since is not None:
        stmt = stmt.where(Cs2Match.match_time >= since)
    rows = list(await session.scalars(stmt))
    return [row for row in rows if str(steam_id) in row.steam_ids()]


__all__ = [
    "get_by_share_code",
    "matches_for_steam_id",
    "metrics_from_line",
    "store",
]
