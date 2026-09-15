"""Fingerprint capture + collusion co-entry check (DB-backed).

Also exercises migration 0033 via the real chain.
"""

from __future__ import annotations

from moneymatch_api.services import fingerprint_service as fp
from tests.factories import create_user


async def test_records_signals_idempotently(session):
    from sqlalchemy import func, select

    from moneymatch_api.models.player_fingerprint import PlayerFingerprint

    u = await create_user(session)
    sig = fp.build_signals(device_id="DEV-1", ip="1.2.3.4")
    await fp.record_signals(session, u.id, sig)
    await fp.record_signals(session, u.id, sig)  # again → no dup
    n = await session.scalar(
        select(func.count())
        .select_from(PlayerFingerprint)
        .where(PlayerFingerprint.player_id == u.id)
    )
    assert n == 2  # device + ip, each once


async def test_shared_device_blocks_co_entry(session):
    a = await create_user(session)
    b = await create_user(session)
    # Both on the same device.
    await fp.record_signals(
        session, a.id, fp.build_signals(device_id="SHARED", ip="1.1.1.1")
    )
    await fp.record_signals(
        session, b.id, fp.build_signals(device_id="SHARED", ip="2.2.2.2")
    )
    # b cannot co-enter a contest a is already in.
    assert await fp.can_co_enter(session, b.id, [a.id]) is False


async def test_distinct_devices_can_co_enter(session):
    a = await create_user(session)
    b = await create_user(session)
    await fp.record_signals(
        session, a.id, fp.build_signals(device_id="D-A", ip="1.1.1.1")
    )
    await fp.record_signals(
        session, b.id, fp.build_signals(device_id="D-B", ip="2.2.2.2")
    )
    assert await fp.can_co_enter(session, b.id, [a.id]) is True


async def test_missing_fingerprint_never_blocks(session):
    a = await create_user(session)
    b = await create_user(session)  # no signals recorded for b
    await fp.record_signals(
        session, a.id, fp.build_signals(device_id="D-A", ip="1.1.1.1")
    )
    assert await fp.can_co_enter(session, b.id, [a.id]) is True


async def test_empty_field_always_allows(session):
    a = await create_user(session)
    assert await fp.can_co_enter(session, a.id, []) is True
