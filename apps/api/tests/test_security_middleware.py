"""Security hardening: headers on every response, an oversized body rejected with
413, and write requests rate-limited with 429.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from moneymatch_api.config import get_settings
from moneymatch_api.main import create_app


@pytest_asyncio.fixture
async def hardened_client() -> AsyncClient:
    settings = get_settings().model_copy(
        update={"rate_limit_writes_per_minute": 2, "max_request_bytes": 100}
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_security_headers_on_every_response(hardened_client: AsyncClient) -> None:
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
    for _ in range(5):
        r = await hardened_client.get("/api/v1/does-not-exist")
        assert r.status_code != 429


async def _post_as(client: AsyncClient, sub: str | None):
    from .conftest import auth_headers

    headers = auth_headers(sub) if sub else {}
    return await client.post("/api/v1/does-not-exist", content=b"{}", headers=headers)


async def test_rate_limit_is_per_user(hardened_client: AsyncClient) -> None:
    for _ in range(2):
        assert (await _post_as(hardened_client, "rl-a")).status_code != 429
    assert (await _post_as(hardened_client, "rl-a")).status_code == 429
    assert (await _post_as(hardened_client, "rl-b")).status_code != 429
    assert (await _post_as(hardened_client, None)).status_code != 429


async def test_invalid_token_falls_back_to_ip(hardened_client: AsyncClient) -> None:
    bad = {"Authorization": "Bearer not-a-jwt"}
    for _ in range(2):
        r = await hardened_client.post("/api/v1/x", content=b"{}", headers=bad)
        assert r.status_code != 429
    anon = await hardened_client.post("/api/v1/x", content=b"{}")
    assert anon.status_code == 429
