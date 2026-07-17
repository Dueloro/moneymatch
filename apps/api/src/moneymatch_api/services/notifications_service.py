"""Notifications — the consolidated fan-out (writes) + the Inbox reads.

Every lifecycle event appends a row inside the transition that causes it
(`match_found`, `settled`, `refund`, `challenge_received`, `challenge_accepted`,
`friend_request`, `room_filled`, `system` — 08-phase-5 · deliverable 7); the
Inbox (`GET /notifications`) consumes them and marks them read. Flushes, never
commits — the caller owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import Notification

_DEFAULT_LIMIT = 50


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


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = _DEFAULT_LIMIT
) -> list[Notification]:
    """Recent notifications, newest first (backs the Inbox screen)."""
    rows = await session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Unread notifications for the sidebar bell dot."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )


async def mark_read(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    ids: list[uuid.UUID] | None = None,
) -> int:
    """Mark the given notifications (or all) read. Idempotent: only unread rows
    are stamped, so a second call is a no-op. Returns the resulting unread count."""
    conds = [Notification.user_id == user_id, Notification.read_at.is_(None)]
    if ids is not None:
        conds.append(Notification.id.in_(ids))
    await session.execute(
        update(Notification).where(*conds).values(read_at=datetime.now(UTC))
    )
    await session.flush()
    return await unread_count(session, user_id)
