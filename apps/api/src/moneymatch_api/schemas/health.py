"""Health-check response schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkerHealth(BaseModel):
    heartbeat_at: datetime | None
    stale: bool


class HealthResponse(BaseModel):
    status: str
    env: str
    version: str
    games: list[str]
    flags: dict[str, bool]
    worker: WorkerHealth
