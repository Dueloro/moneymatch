"""An unhandled exception must exit as a JSON `500` that still carries CORS (and
security) headers.

Starlette's ServerErrorMiddleware sits outside CORSMiddleware, so without our
ExceptionEnvelopeMiddleware a crash ships a raw 500 with no
`Access-Control-Allow-Origin` — the browser then blocks it and the SPA only sees
"Failed to fetch" instead of a readable error (the demo-login symptom)."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from moneymatch_api.config import get_settings
from moneymatch_api.main import create_app

# The CORS allow-list default (config.web_origin); echoed back on an allowed call.
ALLOWED_ORIGIN = "http://localhost:5173"


@pytest_asyncio.fixture
async def boom_client() -> AsyncClient:
    app = create_app(get_settings())

    # A route that raises *after* the middleware stack is entered but needs no DB
    # or auth — a clean stand-in for any handler that throws unexpectedly.
    @app.get("/api/v1/_boom")
    async def _boom() -> None:  # pragma: no cover - body is the raise
        raise RuntimeError("kaboom")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_unhandled_error_is_json_500(boom_client: AsyncClient) -> None:
    r = await boom_client.get("/api/v1/_boom", headers={"Origin": ALLOWED_ORIGIN})
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["code"] == "internal_error"


async def test_unhandled_error_keeps_cors_header(boom_client: AsyncClient) -> None:
    # The whole point: the 500 is still readable cross-origin.
    r = await boom_client.get("/api/v1/_boom", headers={"Origin": ALLOWED_ORIGIN})
    assert r.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


async def test_unhandled_error_keeps_security_headers(boom_client: AsyncClient) -> None:
    # Proof it flowed back out through the full stack, not just CORS.
    r = await boom_client.get("/api/v1/_boom", headers={"Origin": ALLOWED_ORIGIN})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
