"""Feature-flag reads and admin writes.

Flags live in the `feature_flags` DB table (00-README §3.10) so admins can flip
them without a deploy. The read path (`get_boolean_flags`) is per-request/cycle,
so a flip takes effect on the very next call with no restart (09-phase-6 · the
"flag flips take effect without restart" test). Writes go through `set_flag` /
`set_flag_payload` from the admin surface; each is audited by its caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    FLAG_QUEUE_PAUSED,
    FLAG_SETTLEMENT_PAUSED,
    FLAG_WORKER_HEARTBEAT,
    REGISTERED_GAMES,
    game_flag_key,
)
from ..models.feature_flag import FeatureFlag

log = structlog.get_logger(__name__)

# Fallback used before the table exists / when the DB is unreachable, so /health
# stays a liveness probe rather than a DB dependency.
DEFAULT_FLAGS: dict[str, bool] = {
    FLAG_QUEUE_PAUSED: False,
    FLAG_SETTLEMENT_PAUSED: False,
    **{game_flag_key(g): True for g in REGISTERED_GAMES},
}


async def get_boolean_flags(session: AsyncSession) -> dict[str, bool]:
    """Return the boolean feature flags, falling back to defaults on error."""
    try:
        result = await session.execute(select(FeatureFlag))
        rows = result.scalars().all()
    except SQLAlchemyError as exc:
        log.warning("feature_flags.read_failed", error=str(exc))
        return dict(DEFAULT_FLAGS)

    flags = dict(DEFAULT_FLAGS)
    for row in rows:
        flags[row.key] = bool(row.enabled)
    return flags


async def list_flags(session: AsyncSession) -> list[FeatureFlag]:
    """Every flag row (key, enabled, payload) for the admin flags table."""
    result = await session.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    return list(result.scalars().all())


async def get_flag(session: AsyncSession, key: str) -> FeatureFlag | None:
    return await session.scalar(select(FeatureFlag).where(FeatureFlag.key == key))


async def set_flag(
    session: AsyncSession,
    key: str,
    *,
    enabled: bool | None = None,
    payload: dict[str, Any] | None = None,
) -> FeatureFlag:
    """Upsert a flag's `enabled` and/or `payload`. Flushes, never commits.

    Upsert (not update) so a flag the first migration didn't seed (a new
    per-game key, `worker_heartbeat`) can still be set by admin without a
    migration. Read is per-request, so the change is live immediately.
    """
    values: dict[str, Any] = {"key": key}
    if enabled is not None:
        values["enabled"] = enabled
    if payload is not None:
        values["payload"] = payload
    set_on_conflict = {k: v for k, v in values.items() if k != "key"}
    if set_on_conflict:
        stmt = (
            pg_insert(FeatureFlag)
            .values(**values)
            .on_conflict_do_update(index_elements=["key"], set_=set_on_conflict)
        )
    else:
        stmt = pg_insert(FeatureFlag).values(**values).on_conflict_do_nothing()
    await session.execute(stmt)
    await session.flush()
    row = await get_flag(session, key)
    assert row is not None
    return row


async def get_worker_heartbeat(session: AsyncSession) -> datetime | None:
    """The settlement worker's last-cycle timestamp, or None if never written."""
    try:
        flag = await get_flag(session, FLAG_WORKER_HEARTBEAT)
    except SQLAlchemyError as exc:
        log.warning("worker_heartbeat.read_failed", error=str(exc))
        return None
    if flag is None:
        return None
    ts = (flag.payload or {}).get("ts")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
