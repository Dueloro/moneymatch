"""`/admin/disputes` — review and resolve user-filed contest disputes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...services import dispute_service

router = APIRouter(prefix="/disputes", tags=["admin"])


class AdminDisputeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ref_type: str  # match | pool | tournament
    ref_id: UUID
    user_id: UUID
    reason: str
    status: str
    admin_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class ResolveDisputeRequest(BaseModel):
    status: str = Field(..., pattern="^(resolved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


@router.get("", response_model=list[AdminDisputeItem])
async def list_open_disputes(
    _admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> list[AdminDisputeItem]:
    return [
        AdminDisputeItem.model_validate(d)
        for d in await dispute_service.list_open(session)
    ]


@router.post("/{dispute_id}/resolve", response_model=AdminDisputeItem)
async def resolve_dispute(
    dispute_id: UUID,
    body: ResolveDisputeRequest,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> AdminDisputeItem:
    dispute = await dispute_service.resolve(
        session, dispute_id, status=body.status, note=body.note
    )
    return AdminDisputeItem.model_validate(dispute)
