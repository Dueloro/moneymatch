"""`/events/stream` — a Server-Sent Events stream of contest lifecycle events."""

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
_HEARTBEAT_SECONDS = 15
_TICKET_TTL_SECONDS = 30

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
    now = time.monotonic()
    _prune(now)
    entry = _tickets.pop(ticket, None)
    if entry is None or entry[1] <= now:
        raise APIError(
            "unauthorized", "Invalid or expired SSE ticket.", status_code=401
        )
    return entry[0]


def _raw_dsn() -> str:
    return get_settings().database_url.replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


@router.get("/events/stream")
async def stream(request: Request, ticket: str = Query(...)) -> StreamingResponse:
    user_id = _consume_ticket(ticket)

    async def event_gen() -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        conn = await asyncpg.connect(dsn=_raw_dsn())

        def _on_notify(_conn: object, _pid: int, _channel: str, payload: str) -> None:
            queue.put_nowait(payload)

        await conn.add_listener(_CHANNEL, _on_notify)
        try:
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
                if data.get("user_id") != user_id:
                    continue
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
            "X-Accel-Buffering": "no",
        },
    )
