"""SSE ticket exchange: single-use, short-lived, and never the access token."""

from __future__ import annotations

import time

import pytest

from moneymatch_api.errors import APIError
from moneymatch_api.routers import events

pytestmark = pytest.mark.asyncio


class _User:
    id = "user-123"


async def test_ticket_is_single_use():
    events._tickets.clear()
    res = await events.issue_ticket(_User())
    ticket = res["ticket"]

    assert events._consume_ticket(ticket) == "user-123"
    with pytest.raises(APIError):
        events._consume_ticket(ticket)


async def test_expired_or_unknown_ticket_rejected():
    events._tickets.clear()
    with pytest.raises(APIError):
        events._consume_ticket("never-issued")

    events._tickets["stale"] = ("user-9", time.monotonic() - 1)
    with pytest.raises(APIError):
        events._consume_ticket("stale")
    assert "stale" not in events._tickets


async def test_streams_share_one_listener_and_only_get_their_own_events(session):
    import asyncio
    import uuid

    from moneymatch_api.services import notifications_service

    from .factories import create_user

    alice = await create_user(session, username="ev_alice")
    bob = await create_user(session, username="ev_bob")
    hub = events._Hub()
    a1 = await hub.subscribe(str(alice.id))
    conn = hub._conn
    a2 = await hub.subscribe(str(alice.id))
    b = await hub.subscribe(str(bob.id))
    assert hub._conn is conn

    await notifications_service.emit(
        session, alice.id, "refund", {"x": str(uuid.uuid4())}
    )
    await session.commit()

    for queue in (a1, a2):
        payload = await asyncio.wait_for(queue.get(), timeout=5)
        assert str(alice.id) in payload
    assert b.empty()

    await hub.unsubscribe(str(alice.id), a1)
    await hub.unsubscribe(str(alice.id), a2)
    assert not conn.is_closed()
    await hub.unsubscribe(str(bob.id), b)
    assert conn.is_closed() and hub._conn is None
