"""Admin audit trail."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.admin_audit import AdminAudit


async def record(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID,
    action: str,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AdminAudit:
    """Append an audit row for an admin action."""
    row = AdminAudit(
        admin_id=admin_id,
        action=action,
        target=target,
        detail=detail or {},
    )
    session.add(row)
    await session.flush()
    return row
