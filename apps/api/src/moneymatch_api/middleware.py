"""Structured request logging."""

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
    """Catching here (the innermost user middleware) means the synthetic 500 flows
    back out through request logging, the security headers, and CORS — so it is
    logged and carries the right headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 — last-resort net; re-shaped as 500
            log.exception(
                "http.unhandled", method=request.method, path=request.url.path
            )
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
