"""The `/admin` router tree (09-phase-6).

One aggregating router, gated at the router level on `require_admin` so **every**
`/admin/*` route is admin-only — a non-admin never reaches a handler. Sub-routers
(flags, users, contests, queue, reconciliation, risk) are plain operator surfaces;
each mutation writes an `admin_audit` row via `admin_audit_service`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...dependencies import require_admin
from . import contests, flags, queue, reconciliation, risk, users

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

router.include_router(flags.router)
router.include_router(users.router)
router.include_router(contests.router)
router.include_router(queue.router)
router.include_router(reconciliation.router)
router.include_router(risk.router)
