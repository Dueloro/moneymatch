"""The `/admin` router tree."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...dependencies import require_admin
from . import contests, disputes, flags, queue, reconciliation, risk, support, users

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
router.include_router(disputes.router)
router.include_router(support.router)
