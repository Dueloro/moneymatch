"""Structured request logging (09-phase-6 · deliverable 4).

One JSON line per request with method, path, status, duration, and the resolved
user id when the auth dependency ran (it stashes the user on `request.state`).
A per-request id is bound into structlog's contextvars so every log line emitted
while handling the request carries it — the thread that ties a Sentry event, a
worker action, and a settlement together.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger("request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            # A plain string stashed by the auth dependency — never the ORM
            # instance (it is detached once the request session has closed).
            user_id = getattr(request.state, "user_id", None)
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=duration_ms,
                user_id=user_id,
            )
            structlog.contextvars.clear_contextvars()
