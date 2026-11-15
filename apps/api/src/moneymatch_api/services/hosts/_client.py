"""Shared async HTTP helper for the host game clients."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .errors import HostError, HostNotFound, HostRateLimited, HostUnavailable

log = structlog.get_logger(__name__)

_MAX_ATTEMPTS = 3
_DEFAULT_TIMEOUT = 8.0


def _slow_host_ms() -> int:
    from ...config import get_settings

    return get_settings().slow_host_ms


_shared: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None


def _http() -> httpx.AsyncClient:
    """One pooled client per event loop, so calls reuse the TLS connection."""
    global _shared
    loop = asyncio.get_running_loop()
    if _shared is None or _shared[0] is not loop or _shared[1].is_closed:
        _shared = (loop, httpx.AsyncClient())
    return _shared[1]


async def aclose() -> None:
    global _shared
    if _shared is not None:
        shared, _shared = _shared, None
        if shared[0] is asyncio.get_running_loop():
            await shared[1].aclose()


async def request_json(
    host: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT,
    retry: bool = True,
) -> httpx.Response:
    attempt = 0
    async for attempt_ctx in AsyncRetrying(
        stop=stop_after_attempt(_MAX_ATTEMPTS if retry else 1),
        wait=wait_random_exponential(multiplier=0.2, max=2.0),
        retry=(
            retry_if_exception_type(HostUnavailable)
            & retry_if_not_exception_type(HostRateLimited)
        ),
        reraise=True,
    ):
        with attempt_ctx:
            attempt += 1
            started = time.perf_counter()
            status_code: int | None = None
            try:
                response = await _http().request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    timeout=timeout_s,
                )
                status_code = response.status_code
            except httpx.HTTPError as exc:
                raise HostUnavailable(host, f"request failed: {exc}") from exc
            finally:
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                log.info(
                    "host.request",
                    host=host,
                    method=method,
                    url=url,
                    status=status_code,
                    attempt=attempt,
                    latency_ms=latency_ms,
                )
                if latency_ms > _slow_host_ms():
                    log.warning(
                        "host.slow",
                        host=host,
                        url=url,
                        latency_ms=latency_ms,
                        threshold_ms=_slow_host_ms(),
                    )
            if response.status_code == 404:
                raise HostNotFound(host, f"{method} {url} -> 404", 404)
            if response.status_code >= 500:
                raise HostUnavailable(
                    host,
                    f"{method} {url} -> {response.status_code}",
                    response.status_code,
                )
            if response.status_code == 429:
                raise HostRateLimited(host, f"{method} {url} -> 429", 429)
            if response.status_code >= 400:
                raise HostError(
                    host,
                    f"{method} {url} -> {response.status_code}",
                    response.status_code,
                )
            return response
    raise HostUnavailable(host, "retry loop exhausted")  # pragma: no cover
