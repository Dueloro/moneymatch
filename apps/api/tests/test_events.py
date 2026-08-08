"""SSE ticket exchange: single-use, short-lived, and never the access token."""

from __future__ import annotations

import time

import pytest

from moneymatch_api.errors import APIError
from moneymatch_api.routers import events

pytestmark = pytest.mark.asyncio


class _User:
    """Duck-typed stand-in for the CurrentUser dependency (only `.id` is read)."""

    id = "user-123"


async def test_ticket_is_single_use():
    events._tickets.clear()
    res = await events.issue_ticket(_User())
    ticket = res["ticket"]

    assert events._consume_ticket(ticket) == "user-123"
    # A second use is rejected — the ticket was consumed on first connect.
    with pytest.raises(APIError):
        events._consume_ticket(ticket)


async def test_expired_or_unknown_ticket_rejected():
    events._tickets.clear()
    # Unknown ticket → 401.
    with pytest.raises(APIError):
        events._consume_ticket("never-issued")

    # Expired ticket → 401 (and pruned).
    events._tickets["stale"] = ("user-9", time.monotonic() - 1)
    with pytest.raises(APIError):
        events._consume_ticket("stale")
    assert "stale" not in events._tickets
