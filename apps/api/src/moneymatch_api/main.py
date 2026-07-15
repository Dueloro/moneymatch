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
from .routers import health, me

log = structlog.get_logger(__name__)

API_V1_PREFIX = "/api/v1"


def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
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

    return app


# Module-level app for `uvicorn moneymatch_api.main:app`.
app = create_app()
