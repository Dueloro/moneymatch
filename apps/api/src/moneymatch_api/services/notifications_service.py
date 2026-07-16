"""Notification writes (01-architecture §2 · notifications).

Phase 3 emits `match_found` (pairing), `settled` (winner/push), and `refund`
(cancel/expiry) rows inside the transition that causes them; the Phase 5 Inbox
consumes them. This is write-only here (the read/mark-read path lands with the
Inbox). Flushes, never commits — the caller owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import Notification


async def emit(
    session: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
) -> Notification:
    """Append one notification row for a user."""
    row = Notification(user_id=user_id, kind=kind, payload=payload)
    session.add(row)
    await session.flush()
    return row
