"""`/admin/risk` — rate-drift monitor + the sandbagging flag queue.

Read the actual-vs-expected rates per market/difficulty, and clear a risk flag
(freeze the user via `/admin/users/{id}/freeze`). Clearing is audited (09-phase-6
· deliverable 2 · Risk view)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...errors import APIError
from ...schemas.admin import (
    ActionResult,
    RiskFlagRow,
    RiskRateRow,
    RiskResponse,
)
from ...services import admin_audit_service, admin_risk_service

router = APIRouter(tags=["admin"])


@router.get("/risk", response_model=RiskResponse)
async def risk(
    _admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> RiskResponse:
    view = await admin_risk_service.risk_view(session)
    return RiskResponse(
        rates=[
            RiskRateRow(
                game=r.game,
                market=r.market,
                offered=r.offered,
                accepted=r.accepted,
                settled=r.settled,
                expected_rate=r.expected_rate,
                actual_rate=r.actual_rate,
                rake_cents=r.rake_cents,
                dispute_count=r.dispute_count,
                alert=r.alert,
            )
            for r in view.rates
        ],
        flags=[
            RiskFlagRow(
                id=f.id,
                user_id=f.user_id,
                username=f.username,
                game=f.game,
                metric=f.metric,
                kind=f.kind,
                detail=f.detail,
                created_at=f.created_at,
            )
            for f in view.flags
        ],
    )


@router.post("/risk/flags/{flag_id}/clear", response_model=ActionResult)
async def clear_flag(
    flag_id: UUID,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ActionResult:
    flag = await admin_risk_service.clear_flag(session, flag_id)
    if flag is None:
        raise APIError("flag_not_found", "No such risk flag.", status_code=404)
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="risk_flag.clear",
        target=str(flag_id),
        detail={"user_id": str(flag.user_id), "kind": flag.kind},
    )
    return ActionResult()
