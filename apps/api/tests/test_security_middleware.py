"""Security hardening (10-phase-7 §2): headers on every response, an oversized
body rejected with 413, and write requests rate-limited with 429."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from moneymatch_api.config import get_settings
from moneymatch_api.main import create_app


@pytest_asyncio.fixture
async def hardened_client() -> AsyncClient:
    # A tiny rate window + body cap so the limits are cheap to exercise.
    settings = get_settings().model_copy(
        update={"rate_limit_writes_per_minute": 2, "max_request_bytes": 100}
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_security_headers_on_every_response(hardened_client: AsyncClient) -> None:
    # A 404 needs no DB/auth and still exits through the header middleware.
    r = await hardened_client.get("/api/v1/does-not-exist")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"] == "no-referrer"


async def test_oversized_body_rejected(hardened_client: AsyncClient) -> None:
    r = await hardened_client.post("/api/v1/does-not-exist", content=b"x" * 500)
    assert r.status_code == 413
    assert r.json()["code"] == "request_too_large"


async def test_write_rate_limit(hardened_client: AsyncClient) -> None:
    # Under the small body cap so we exercise the limiter, not the size guard.
    body = {"content": b"{}"}
    ok1 = await hardened_client.post("/api/v1/does-not-exist", **body)
    ok2 = await hardened_client.post("/api/v1/does-not-exist", **body)
    limited = await hardened_client.post("/api/v1/does-not-exist", **body)
    assert ok1.status_code != 429
    assert ok2.status_code != 429
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["retry-after"] == "60"


async def test_reads_not_rate_limited(hardened_client: AsyncClient) -> None:
    # GETs bypass the write limiter entirely.
    for _ in range(5):
        r = await hardened_client.get("/api/v1/does-not-exist")
        assert r.status_code != 429
