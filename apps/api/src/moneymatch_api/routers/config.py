"""Public client config: the server's own values, so the web app keeps no copies."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..models.wallet import DEMO_DEPOSIT_PRESETS_CENTS
from ..services import geo_service, money_math

router = APIRouter(tags=["config"])


class ClientConfig(BaseModel):
    excluded_states: list[str]
    rake_bps: int
    deposit_presets_cents: list[int]


@router.get("/config", response_model=ClientConfig)
async def client_config(session: AsyncSession = Depends(get_session)) -> ClientConfig:
    return ClientConfig(
        excluded_states=sorted(await geo_service.excluded_states(session)),
        rake_bps=money_math.DEFAULT_RAKE_BPS,
        deposit_presets_cents=list(DEMO_DEPOSIT_PRESETS_CENTS),
    )
