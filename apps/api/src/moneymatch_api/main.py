"""FastAPI application factory.

Wires config → logging → Sentry → middleware → routers. The API is a stateless,
long-running service (00-README §2); nothing durable lives in process memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .db.session import dispose_engine
from .errors import register_error_handlers
from .logging import configure_logging
from .middleware import RequestLogMiddleware
from .routers import (
    activity,
    admin,
    challenges,
    friends,
    health,
    leaderboard,
    links,
    me,
    notifications,
    play,
    pools,
    tournaments,
    wallet,
)
from .security import (
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)

log = structlog.get_logger(__name__)

API_V1_PREFIX = "/api/v1"


def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.release,
        traces_sample_rate=0.0,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("api.startup")
    yield
    await dispose_engine()
    log.info("api.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    _init_sentry(settings)

    app = FastAPI(
        title="MoneyMatch API",
        version="0.0.0",
        lifespan=lifespan,
    )

    # Middleware wrap inner→outer in add order (last added = outermost). The
    # target chain, outer→inner, is: CORS → security headers → rate limit →
    # body-size cap → request log → app, so every response (including an early
    # 413/429) still carries CORS + security headers (10-phase-7 §2).
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        RateLimitMiddleware, per_minute=settings.rate_limit_writes_per_minute
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(health.router, prefix=API_V1_PREFIX)
    app.include_router(me.router, prefix=API_V1_PREFIX)
    app.include_router(wallet.router, prefix=API_V1_PREFIX)
    app.include_router(links.router, prefix=API_V1_PREFIX)
    app.include_router(play.router, prefix=API_V1_PREFIX)
    app.include_router(pools.router, prefix=API_V1_PREFIX)
    app.include_router(tournaments.router, prefix=API_V1_PREFIX)
    app.include_router(activity.router, prefix=API_V1_PREFIX)
    app.include_router(friends.router, prefix=API_V1_PREFIX)
    app.include_router(challenges.router, prefix=API_V1_PREFIX)
    app.include_router(leaderboard.router, prefix=API_V1_PREFIX)
    app.include_router(notifications.router, prefix=API_V1_PREFIX)
    app.include_router(admin.router, prefix=API_V1_PREFIX)

    return app


# Module-level app for `uvicorn moneymatch_api.main:app`.
app = create_app()
