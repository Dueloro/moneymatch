"""`/events/stream` — a Server-Sent Events stream of contest lifecycle events."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..dependencies import CurrentUser
from ..errors import APIError
from ..services.notifications_service import EVENTS_CHANNEL

log = structlog.get_logger(__name__)

router = APIRouter(tags=["events"])

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


class _Hub:
    """One LISTEN connection per process, fanned out to every open stream.

    A connection per stream would exhaust a small Postgres plan's connection limit.
    """

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[str | None]]] = {}
        self._conn: Any = None
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: str) -> asyncio.Queue[str | None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=100)
        async with self._lock:
            if self._conn is None or self._conn.is_closed():
                conn = await asyncpg.connect(dsn=_raw_dsn())
                await conn.add_listener(EVENTS_CHANNEL, self._on_notify)
                conn.add_termination_listener(self._on_lost)
                self._conn = conn
            self._queues.setdefault(user_id, set()).add(queue)
        return queue

    async def unsubscribe(self, user_id: str, queue: asyncio.Queue[str | None]) -> None:
        async with self._lock:
            queues = self._queues.get(user_id)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    del self._queues[user_id]
            if not self._queues and self._conn is not None:
                conn, self._conn = self._conn, None
                conn.remove_termination_listener(self._on_lost)
                await conn.close()

    def _on_notify(self, _conn: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            user_id = json.loads(payload).get("user_id")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return
        for queue in self._queues.get(user_id, ()):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _on_lost(self, _conn: object) -> None:
        # End every stream; the browser reconnects and the next subscribe re-listens.
        self._conn = None
        for queues in self._queues.values():
            for queue in queues:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass


hub = _Hub()


@router.get("/events/stream")
async def stream(request: Request, ticket: str = Query(...)) -> StreamingResponse:
    user_id = _consume_ticket(ticket)

    async def event_gen() -> AsyncIterator[str]:
        queue = await hub.subscribe(user_id)
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
                if payload is None:
                    break
                yield f"data: {payload}\n\n"
        finally:
            await hub.unsubscribe(user_id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
