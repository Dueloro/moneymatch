"""Identity-fingerprint capture + collusion co-entry check (Phase 6 wiring).

Bridges the pure `collusion` predicates to the DB: it records the signals a
client presents (a device id from a header, the request IP), and answers "may
this player join a contest that these other players are already in?" by looking
for a shared signal — the same-human block.

Signals are opaque namespaced tokens ("device:...", "ip:...") so a device id can
never collide with an IP, and an unknown/blank signal never matches (we never
block a player for *lacking* a fingerprint — only a positive overlap blocks).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player_fingerprint import PlayerFingerprint
from . import collusion


def build_signals(*, device_id: str | None, ip: str | None) -> list[str]:
    """Normalized signal tokens from a request's device header + client IP."""
    return list(collusion.make_fingerprint(device_id=device_id, ip=ip))


async def record_signals(
    session: AsyncSession, player_id: uuid.UUID, signals: Iterable[str]
) -> None:
    """Upsert each presented signal for the player (idempotent; refreshes
    last_seen). Never raises on a duplicate — it's derived, best-effort data."""
    for signal in signals:
        if not signal:
            continue
        ins = pg_insert(PlayerFingerprint).values(player_id=player_id, signal=signal)
        stmt = ins.on_conflict_do_update(
            constraint="uq_player_fingerprint_player_signal",
            set_={"last_seen_at": ins.excluded.last_seen_at},
        )
        await session.execute(stmt)
    await session.flush()


async def _signals_for(
    session: AsyncSession, player_id: uuid.UUID
) -> frozenset[str]:
    rows = await session.scalars(
        select(PlayerFingerprint.signal).where(
            PlayerFingerprint.player_id == player_id
        )
    )
    return frozenset(rows)


async def can_co_enter(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    existing_ids: Iterable[uuid.UUID],
) -> bool:
    """Whether `candidate_id` may join a contest the `existing_ids` are already in
    — i.e. it shares no identity signal with any of them. Missing fingerprints on
    either side simply don't match, so nobody is blocked for lacking one."""
    others = [pid for pid in existing_ids if pid != candidate_id]
    if not others:
        return True
    candidate = await _signals_for(session, candidate_id)
    if not candidate:
        return True
    existing = [await _signals_for(session, pid) for pid in others]
    return collusion.can_co_enter(candidate, existing)
