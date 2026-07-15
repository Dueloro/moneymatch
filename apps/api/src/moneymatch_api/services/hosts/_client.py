"""Shared async HTTP helper for the host game clients.

One place for the port changes the phase doc mandates (05-phase-2 · deliverable 1):

- explicit timeouts + a bounded retry with jittered backoff (tenacity, 2 retries)
  on transport errors / 5xx — a 4xx is never retried;
- typed upstream errors (`HostUnavailable` / `HostNotFound`) instead of raw
  `httpx` exceptions;
- host latency logged (structlog) on every call for ops.

Each process (api, worker) builds its own transient `AsyncClient` per call — no
shared pool state across the two — which keeps this dependency-free and matches
the PoC's per-call client usage.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .errors import HostNotFound, HostUnavailable

log = structlog.get_logger(__name__)

# 2 retries ⇒ 3 attempts total, with jittered exponential backoff so a briefly
# flapping host doesn't turn into a thundering herd.
_MAX_ATTEMPTS = 3
_DEFAULT_TIMEOUT = 8.0


async def request_json(
    host: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT,
) -> httpx.Response:
    """Perform a request, returning the 2xx `httpx.Response`.

    Raises `HostNotFound` on 404 and `HostUnavailable` on 5xx / transport error /
    timeout (after retries). The caller decides whether to fail soft (history
    polls return `[]`) or surface the error (profile lookups map to 404/502).
    """
    attempt = 0
    async for retry in AsyncRetrying(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_random_exponential(multiplier=0.2, max=2.0),
        retry=retry_if_exception_type(HostUnavailable),
        reraise=True,
    ):
        with retry:
            attempt += 1
            started = time.perf_counter()
            status_code: int | None = None
            try:
                async with httpx.AsyncClient(headers=headers) as client:
                    response = await client.request(
                        method, url, params=params, data=data, timeout=timeout_s
                    )
                status_code = response.status_code
            except httpx.HTTPError as exc:
                raise HostUnavailable(host, f"request failed: {exc}") from exc
            finally:
                log.info(
                    "host.request",
                    host=host,
                    method=method,
                    url=url,
                    status=status_code,
                    attempt=attempt,
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            if response.status_code == 404:
                raise HostNotFound(host, f"{method} {url} → 404")
            if response.status_code >= 500:
                raise HostUnavailable(host, f"{method} {url} → {response.status_code}")
            response.raise_for_status()
            return response
    # Unreachable: reraise=True re-raises the last error rather than exiting.
    raise HostUnavailable(host, "retry loop exhausted")  # pragma: no cover
