"""`/admin/reconciliation` — on-demand solvency + per-contest conservation.

Runs the global solvency check and sweeps every contest for a conservation
breach; any violating ref comes back with its totals so the UI can render it red
with the ledger trail. Also reports the worker heartbeat (09-phase-6 · d.2/d.4)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...constants import WORKER_HEARTBEAT_STALE_SECONDS
from ...db.session import get_session
from ...dependencies import AdminUser
from ...schemas.admin import (
    ReconciliationResponse,
    ReconViolationRow,
    WorkerStatus,
)
from ...services import feature_flags, reconciliation_service

router = APIRouter(tags=["admin"])


@router.get("/reconciliation", response_model=ReconciliationResponse)
async def reconciliation(
    _admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> ReconciliationResponse:
    solvency = await reconciliation_service.check_all(session)
    contest_violations = await reconciliation_service.check_contests(session)

    heartbeat = await feature_flags.get_worker_heartbeat(session)
    stale = True
    if heartbeat is not None:
        age = (datetime.now(UTC) - heartbeat).total_seconds()
        stale = age > WORKER_HEARTBEAT_STALE_SECONDS

    return ReconciliationResponse(
        ok=solvency.ok and not contest_violations,
        solvency_ok=solvency.ok,
        solvency_violations=solvency.violations,
        totals=solvency.totals,
        contest_violations=[
            ReconViolationRow(
                ref_type=ref_type,
                ref_id=ref_id,
                violations=result.violations,
                totals=result.totals,
            )
            for ref_type, ref_id, result in contest_violations
        ],
        worker=WorkerStatus(heartbeat_at=heartbeat, stale=stale),
    )
