"""Structured request logging (09-phase-6 · deliverable 4).

One JSON line per request with method, path, status, duration, and the resolved
user id when the auth dependency ran (it stashes the user on `request.state`).
A per-request id is bound into structlog's contextvars so every log line emitted
while handling the request carries it — the thread that ties a Sentry event, a
worker action, and a settlement together.
"""

from __future__ import annotations

import contextlib
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger("request")


class ExceptionEnvelopeMiddleware(BaseHTTPMiddleware):
    """Turn an otherwise-unhandled exception into the standard JSON `500`
    envelope *inside* the app's middleware stack.

    Starlette's `ServerErrorMiddleware` — which would otherwise produce the 500 —
    sits *outside* every user middleware, including `CORSMiddleware`. So a raw
    500 ships with no `Access-Control-Allow-Origin` header, the browser blocks the
    cross-origin response, and `fetch` rejects with an opaque "Failed to fetch"
    instead of letting the SPA read the error. Catching here (the innermost user
    middleware) means the synthetic 500 flows back out through request logging,
    the security headers, and CORS — so it is logged and carries the right headers.

    The registered handlers (`APIError` / `HTTPException` / validation) run further
    in, in Starlette's `ExceptionMiddleware`, and are unaffected: only genuinely
    unexpected errors reach this last-resort net.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — last-resort net; re-shaped as 500
            log.exception(
                "http.unhandled", method=request.method, path=request.url.path
            )
            # Preserve Sentry reporting we'd otherwise lose by not re-raising to
            # ServerErrorMiddleware. No-op when Sentry isn't installed/initialised.
            with contextlib.suppress(ImportError):
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            return JSONResponse(
                status_code=500,
                content={
                    "code": "internal_error",
                    "message": "Internal server error.",
                    "detail": None,
                },
            )


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
