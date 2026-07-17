"""Admin audit trail (09-phase-6 · deliverable 1).

Every admin mutation writes an `admin_audit` row — no exceptions. This module is
the single write path; routers call `record()` inside the same transaction as the
mutation they are logging, so an action and its audit row commit together (or not
at all). Reads never audit; only state-changing actions do.
"""

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
    """Append an audit row for an admin action. Flushes, never commits."""
    row = AdminAudit(
        admin_id=admin_id,
        action=action,
        target=target,
        detail=detail or {},
    )
    session.add(row)
    await session.flush()
    return row
