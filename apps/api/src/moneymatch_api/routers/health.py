"""Public health endpoint: service liveness + registered games + flags."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import __version__
from ..adapters import registry
from ..config import get_settings
from ..constants import WORKER_HEARTBEAT_STALE_SECONDS
from ..db.session import get_session
from ..schemas.health import HealthResponse, WorkerHealth
from ..services import feature_flags
from ..services.feature_flags import get_boolean_flags

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    settings = get_settings()
    flags = await get_boolean_flags(session)
    heartbeat = await feature_flags.get_worker_heartbeat(session)
    stale = True
    if heartbeat is not None:
        stale = (
            datetime.now(UTC) - heartbeat
        ).total_seconds() > WORKER_HEARTBEAT_STALE_SECONDS
    # `status` stays "ok" for liveness (the API is up); the worker's staleness is
    # the red signal ops/admin read (09-phase-6 · deliverable 4).
    return HealthResponse(
        status="ok",
        env=settings.env,
        version=__version__,
        # Registered games come from the adapter registry, filtered by flags —
        # a disabled game:<id> flag drops the game here too (05-phase-2 · d.7).
        games=registry.enabled_ids(flags),
        flags=flags,
        worker=WorkerHealth(heartbeat_at=heartbeat, stale=stale),
    )
