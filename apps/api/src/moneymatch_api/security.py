"""Security hardening middleware."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .auth import AuthError, extract_bearer_token, verify_token
from .config import Settings

# Methods that mutate state — the ones worth rate-limiting and body-capping.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    return _error(413, "request_too_large", "Request body too large.")
            except ValueError:
                return _error(400, "invalid_content_length", "Bad Content-Length.")
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-(caller, method, path) cap on write requests.

    The caller is the verified user (same check as `auth.verify_token`) when the
    request carries a valid bearer token, else the client IP. Unverified tokens never
    pick the bucket, so nobody can spend another user's budget.
    """

    WINDOW_SECONDS = 60

    def __init__(
        self, app, *, per_minute: int, settings: Settings | None = None
    ) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self.settings = settings
        self._buckets: dict[str, tuple[int, int]] = {}

    def _client(self, request: Request) -> str:
        authorization = request.headers.get("authorization")
        if authorization:
            try:
                token = extract_bearer_token(authorization)
                return "user:" + verify_token(token, self.settings).auth_id
            except AuthError:
                pass
        return "ip:" + (request.client.host if request.client else "unknown")

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in WRITE_METHODS:
            return await call_next(request)

        now = int(time.time())
        window = now - (now % self.WINDOW_SECONDS)
        key = f"{self._client(request)}:{request.method}:{request.url.path}"
        start, count = self._buckets.get(key, (window, 0))
        if start != window:
            start, count = window, 0
        count += 1
        self._buckets[key] = (start, count)

        if count > self.per_minute:
            resp = _error(429, "rate_limited", "Too many requests; slow down.")
            resp.headers["Retry-After"] = str(self.WINDOW_SECONDS)
            return resp
        return await call_next(request)
