"""Keep a free-tier web service awake so the in-process worker keeps running.

Render's free web services sleep after 15 minutes without an inbound request,
and the worker loop (settlement + background match fetching) sleeps with them:
a tournament would not settle until someone happened to open the site. Calling
our own public health URL every few minutes counts as inbound traffic, so the
service, and the worker inside it, stays up.

Render sets `RENDER_EXTERNAL_URL` on every web service, so this switches itself
on there and stays off locally. One always-on service fits inside the free
tier's monthly instance hours.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger(__name__)

#: Well under the 15-minute idle limit, with room for a missed ping.
KEEP_ALIVE_INTERVAL_SECONDS = 10 * 60


async def run_forever(
    base_url: str, interval: int = KEEP_ALIVE_INTERVAL_SECONDS
) -> None:
    url = f"{base_url.rstrip('/')}/api/v1/health"
    log.info("keep_alive.start", url=url, interval=interval)
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            await asyncio.sleep(interval)
            try:
                r = await client.get(url)
                if r.status_code >= 400:
                    log.warning("keep_alive.bad_status", status=r.status_code)
            except Exception as exc:  # noqa: BLE001 — try again next interval
                log.warning("keep_alive.failed", error=str(exc))
