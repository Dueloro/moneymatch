"""`/admin/contests` — inspect a contest's full money trail and fix it.

List by state/game; detail shows lifecycle + participants + ledger + adapter
evidence + a live reconciliation. Two money-fix actions on matches: `resettle`
(re-runs the worker grade+settle path, idempotent) and `void` (CANCEL + full
refund). Both audited (09-phase-6 · deliverable 2)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...schemas.admin import (
    AdminContestDetail,
    AdminContestListItem,
    AdminContestListResponse,
    ResettleResult,
    VoidRequest,
)
from ...services import admin_audit_service, admin_contests_service

router = APIRouter(tags=["admin"])


@router.get("/contests", response_model=AdminContestListResponse)
async def list_contests(
    _admin: AdminUser,
    state: str | None = Query(default=None),
    game: str | None = Query(default=None),
    ref_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> AdminContestListResponse:
    rows = await admin_contests_service.list_contests(
        session, state=state, game=game, ref_type=ref_type
    )
    return AdminContestListResponse(
        contests=[
            AdminContestListItem(
                ref_type=r.ref_type,
                ref_id=r.ref_id,
                game=r.game,
                market=r.market,
                state=r.state,
                entry_cents=r.entry_cents,
                pot_cents=r.pot_cents,
                participants=r.participants,
                created_at=r.created_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ]
    )


@router.get("/contests/{ref_type}/{ref_id}", response_model=AdminContestDetail)
async def contest_detail(
    ref_type: str,
    ref_id: UUID,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> AdminContestDetail:
    d = await admin_contests_service.contest_detail(session, ref_type, ref_id)
    return AdminContestDetail(
        ref_type=d.ref_type,
        ref_id=d.ref_id,
        game=d.game,
        market=d.market,
        state=d.state,
        entry_cents=d.entry_cents,
        pot_cents=d.pot_cents,
        prize_cents=d.prize_cents,
        rake_cents=d.rake_cents,
        engine_version=d.engine_version,
        outcome_detail=d.outcome_detail,
        created_at=d.created_at,
        resolved_at=d.resolved_at,
        participants=d.participants,
        ledger=d.ledger,
        platform_ledger=d.platform_ledger,
        reconciliation=d.reconciliation,
    )


@router.post("/matches/{match_id}/resettle", response_model=ResettleResult)
async def resettle_match(
    match_id: UUID,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ResettleResult:
    outcome = await admin_contests_service.resettle_match(session, match_id)
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="match.resettle",
        target=str(match_id),
        detail={"outcome": outcome},
    )
    d = await admin_contests_service.contest_detail(session, "match", match_id)
    return ResettleResult(outcome=outcome, state=d.state)


@router.post("/matches/{match_id}/void", response_model=ResettleResult)
async def void_match(
    match_id: UUID,
    body: VoidRequest,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ResettleResult:
    match = await admin_contests_service.void_match(
        session, match_id, reason=body.reason
    )
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="match.void",
        target=str(match_id),
        detail={"reason": body.reason},
    )
    return ResettleResult(outcome="void", state=match.state)
