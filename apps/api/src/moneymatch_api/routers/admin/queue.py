"""`/admin/queue` — live queue depth, mean wait, and expiry rate."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...schemas.admin import QueueDepthRow, QueueResponse
from ...services import admin_queue_service

router = APIRouter(tags=["admin"])


@router.get("/queue", response_model=QueueResponse)
async def queue(
    _admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> QueueResponse:
    stats = await admin_queue_service.queue_stats(session)
    return QueueResponse(
        waiting=stats.waiting,
        matched=stats.matched,
        expired=stats.expired,
        canceled=stats.canceled,
        expiry_rate=stats.expiry_rate,
        depth=[
            QueueDepthRow(
                game=d.game,
                market=d.market,
                entry_cents=d.entry_cents,
                waiting=d.waiting,
                avg_wait_seconds=d.avg_wait_seconds,
            )
            for d in stats.depth
        ],
    )
