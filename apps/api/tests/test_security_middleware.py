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


@pytest_asyncio.fixture
async def proxied_client() -> AsyncClient:
    # Behind one trusted proxy: the limiter must bucket on X-Forwarded-For, not
    # the (shared) socket peer.
    settings = get_settings().model_copy(
        update={"rate_limit_writes_per_minute": 2, "rate_limit_trusted_proxy_hops": 1}
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_rate_limit_buckets_per_forwarded_client(
    proxied_client: AsyncClient,
) -> None:
    # Two distinct real clients arrive via the same proxy. Each gets its own
    # window; one exhausting its cap must not spend the other's.
    a = {"headers": {"x-forwarded-for": "203.0.113.7"}, "content": b"{}"}
    b = {"headers": {"x-forwarded-for": "198.51.100.9"}, "content": b"{}"}
    assert (await proxied_client.post("/api/v1/does-not-exist", **a)).status_code != 429
    assert (await proxied_client.post("/api/v1/does-not-exist", **a)).status_code != 429
    # Client A is now over the cap...
    assert (await proxied_client.post("/api/v1/does-not-exist", **a)).status_code == 429
    # ...but client B, same proxy, is untouched.
    assert (await proxied_client.post("/api/v1/does-not-exist", **b)).status_code != 429


async def test_forwarded_for_ignored_without_trusted_hops(
    hardened_client: AsyncClient,
) -> None:
    # Default posture trusts no proxy hops, so a spoofed X-Forwarded-For can't
    # mint fresh buckets — all requests share the socket-peer bucket and the cap
    # still bites on the third.
    r1 = await hardened_client.post(
        "/api/v1/does-not-exist", headers={"x-forwarded-for": "1.1.1.1"}, content=b"{}"
    )
    r2 = await hardened_client.post(
        "/api/v1/does-not-exist", headers={"x-forwarded-for": "2.2.2.2"}, content=b"{}"
    )
    r3 = await hardened_client.post(
        "/api/v1/does-not-exist", headers={"x-forwarded-for": "3.3.3.3"}, content=b"{}"
    )
    assert r1.status_code != 429
    assert r2.status_code != 429
    assert r3.status_code == 429
