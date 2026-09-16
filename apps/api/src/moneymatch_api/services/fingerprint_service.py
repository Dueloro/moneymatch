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


# Signal kinds strong enough to HARD-BLOCK co-entry on their own. A shared device
# or payment instrument is a strong same-human signal; a shared IP is not (a
# household, campus, or mobile-carrier NAT puts many distinct people on one IP), so
# IP is recorded for review but never blocks a pairing by itself.
_BLOCKING_KINDS = ("device:", "payment:")


def _is_blocking(signal: str) -> bool:
    return signal.startswith(_BLOCKING_KINDS)


async def _signals_for(
    session: AsyncSession, player_id: uuid.UUID, *, blocking_only: bool = False
) -> frozenset[str]:
    rows = await session.scalars(
        select(PlayerFingerprint.signal).where(
            PlayerFingerprint.player_id == player_id
        )
    )
    signals = frozenset(rows)
    if blocking_only:
        return frozenset(s for s in signals if _is_blocking(s))
    return signals


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
    # Only strong signals (device / payment) hard-block; a shared IP alone never
    # does, to avoid blocking legitimate players behind one NAT.
    candidate = await _signals_for(session, candidate_id, blocking_only=True)
    if not candidate:
        return True
    existing = [
        await _signals_for(session, pid, blocking_only=True) for pid in others
    ]
    return collusion.can_co_enter(candidate, existing)
