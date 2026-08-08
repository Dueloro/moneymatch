"""`/events/stream` — a Server-Sent Events stream of contest lifecycle events.

The settlement worker runs in a *separate process*, so an in-process pub/sub
can't reach the API's connections. Instead every `notifications_service.emit`
issues a Postgres `pg_notify` (delivered on COMMIT); this endpoint holds one
dedicated `LISTEN` connection per client and forwards the events addressed to the
authenticated viewer. The browser keeps a single `EventSource` open and refreshes
the Activity feed / rail the instant an event arrives — no client-side polling.

Auth: `EventSource` can't set an `Authorization` header, and putting the
long-lived access token in the `?token=` query string would leak it into access
logs and browser history. So the client first trades its bearer token (sent the
normal way, in the header) for a **single-use, short-lived ticket** via
`POST /events/ticket`, then connects with `?ticket=`. The ticket is a random
opaque string, consumed on connect, and grants nothing but this user's stream.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator

import asyncpg
import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..dependencies import CurrentUser
from ..errors import APIError

log = structlog.get_logger(__name__)

router = APIRouter(tags=["events"])

_CHANNEL = "moneymatch_events"
# Cap the idle wait so we emit an SSE heartbeat (keeps proxies from closing the
# connection) and re-check client disconnect on the same cadence.
_HEARTBEAT_SECONDS = 15
_TICKET_TTL_SECONDS = 30

# Single-use SSE tickets: {ticket -> (user_id, expires_at_monotonic)}.
#
# The store is in-process, which is correct for the single web instance this
# runs on. A horizontally-scaled deployment would move it to Postgres/Redis so a
# ticket minted on one instance can be consumed on another; the endpoint contract
# stays the same.
_tickets: dict[str, tuple[str, float]] = {}


def _prune(now: float) -> None:
    for ticket, (_, expires) in list(_tickets.items()):
        if expires <= now:
            _tickets.pop(ticket, None)


@router.post("/events/ticket")
async def issue_ticket(user: CurrentUser) -> dict[str, object]:
    """Trade the bearer token (header auth) for a single-use SSE ticket."""
    now = time.monotonic()
    _prune(now)
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = (str(user.id), now + _TICKET_TTL_SECONDS)
    return {"ticket": ticket, "expires_in": _TICKET_TTL_SECONDS}


def _consume_ticket(ticket: str) -> str:
    """Pop-and-return the ticket's user_id, or 401 if unknown/expired (one-time)."""
    now = time.monotonic()
    _prune(now)
    entry = _tickets.pop(ticket, None)
    if entry is None or entry[1] <= now:
        raise APIError(
            "unauthorized", "Invalid or expired SSE ticket.", status_code=401
        )
    return entry[0]


def _raw_dsn() -> str:
    """A plain libpq DSN for asyncpg (strip the SQLAlchemy `+asyncpg` marker)."""
    return get_settings().database_url.replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


@router.get("/events/stream")
async def stream(request: Request, ticket: str = Query(...)) -> StreamingResponse:
    # Consume the single-use ticket up front so a bad one fails as a clean 401
    # before we open the stream. The long-lived access token never appears here.
    user_id = _consume_ticket(ticket)

    async def event_gen() -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        conn = await asyncpg.connect(dsn=_raw_dsn())

        def _on_notify(_conn: object, _pid: int, _channel: str, payload: str) -> None:
            queue.put_nowait(payload)

        await conn.add_listener(_CHANNEL, _on_notify)
        try:
            # A comment line so the client's `onopen` fires and proxies flush headers.
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                try:
                    data = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    continue
                # One channel serves every user; only forward this viewer's events.
                if data.get("user_id") != user_id:
                    continue
                # Default (unnamed) SSE message so the client's `onmessage` catches
                # every kind; the `kind` travels inside the JSON `data` for anyone
                # who wants to branch on it.
                yield f"data: {payload}\n\n"
        finally:
            try:
                await conn.remove_listener(_CHANNEL, _on_notify)
            finally:
                await conn.close()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering (nginx) so events flush immediately.
            "X-Accel-Buffering": "no",
        },
    )
