"""FastAPI application factory."""

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
from .middleware import ExceptionEnvelopeMiddleware, RequestLogMiddleware
from .observability import init_sentry
from .routers import (
    activity,
    admin,
    challenges,
    chat,
    disputes,
    events,
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("api.startup")
    settings: Settings = app.state.settings

    if settings.env == "prod":
        # The geo-fence is the one gate that decides whether a stake may be taken at
        # all, and it lives in a database row rather than in code.
        from .db.session import get_sessionmaker
        from .services import geo_service

        async with get_sessionmaker()() as session:
            await geo_service.assert_configured_for_production(session)

    try:
        yield
    finally:
        await dispose_engine()
        log.info("api.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    init_sentry(settings)

    app = FastAPI(
        title="MoneyMatch API",
        version="0.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # The target chain, outer→inner, is: CORS → security headers → rate limit → body-
    # size cap → request log → exception envelope → app, so every response (including an
    # early 413/429) still carries CORS + security headers.
    app.add_middleware(ExceptionEnvelopeMiddleware)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=settings.rate_limit_writes_per_minute,
        settings=settings,
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
    app.include_router(events.router, prefix=API_V1_PREFIX)
    app.include_router(disputes.router, prefix=API_V1_PREFIX)
    app.include_router(friends.router, prefix=API_V1_PREFIX)
    app.include_router(challenges.router, prefix=API_V1_PREFIX)
    app.include_router(chat.router, prefix=API_V1_PREFIX)
    app.include_router(leaderboard.router, prefix=API_V1_PREFIX)
    app.include_router(notifications.router, prefix=API_V1_PREFIX)
    app.include_router(admin.router, prefix=API_V1_PREFIX)

    if settings.e2e_auth_enabled and settings.env != "prod":
        from .routers import dev

        app.include_router(dev.router, prefix=API_V1_PREFIX)
        log.warning("api.e2e_auth_enabled")

    return app


app = create_app()
