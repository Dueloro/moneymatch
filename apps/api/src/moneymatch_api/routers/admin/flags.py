"""`/admin/flags` — kill switches & config, flippable without a deploy.

Toggles per-game enable (`game:<id>`), `queue_paused`, `settlement_paused`, and
edits the `geo_config` excluded-state list. The read path is per-request, so a
flip takes effect on the next API call / worker cycle — no restart (09-phase-6 ·
exit criterion "flag flips verifiably stop the machinery"). Every write is
audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...errors import APIError
from ...schemas.admin import FlagItem, FlagsResponse, UpdateFlagRequest
from ...services import admin_audit_service, feature_flags

router = APIRouter(tags=["admin"])


def _item(row) -> FlagItem:
    return FlagItem(key=row.key, enabled=bool(row.enabled), payload=row.payload or {})


@router.get("/flags", response_model=FlagsResponse)
async def list_flags(
    _admin: AdminUser, session: AsyncSession = Depends(get_session)
) -> FlagsResponse:
    rows = await feature_flags.list_flags(session)
    return FlagsResponse(flags=[_item(r) for r in rows])


@router.put("/flags/{key}", response_model=FlagItem)
async def update_flag(
    key: str,
    body: UpdateFlagRequest,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> FlagItem:
    if body.enabled is None and body.payload is None:
        raise APIError(
            "empty_update",
            "Provide `enabled` and/or `payload`.",
            status_code=422,
        )
    row = await feature_flags.set_flag(
        session, key, enabled=body.enabled, payload=body.payload
    )
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="flag.update",
        target=key,
        detail={"enabled": body.enabled, "payload": body.payload},
    )
    return _item(row)
