"""Token-bucket limiter for the PUBG host client (process-local; ~9 req/min)."""

from __future__ import annotations

import asyncio
import time

from moneymatch_api.services.hosts.pubg import _TokenBucket


async def test_bucket_allows_burst_up_to_capacity_without_waiting():
    bucket = _TokenBucket(rate_per_min=6)  # capacity 6, refill 0.1/s
    started = time.monotonic()
    for _ in range(6):
        await bucket.acquire()
    assert time.monotonic() - started < 0.1  # full bucket → no waiting


async def test_bucket_throttles_once_capacity_is_spent():
    bucket = _TokenBucket(rate_per_min=60)  # capacity 60, refill 1/s
    for _ in range(60):
        await bucket.acquire()
    started = time.monotonic()
    await bucket.acquire()  # 61st must wait ~1s for a refill
    waited = time.monotonic() - started
    assert 0.5 <= waited <= 2.0


async def test_bucket_is_concurrency_safe():
    bucket = _TokenBucket(rate_per_min=6)
    await asyncio.gather(*(bucket.acquire() for _ in range(6)))  # no deadlock
