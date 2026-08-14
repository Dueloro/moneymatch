"""Notifications — the consolidated fan-out (writes) + the Inbox reads.

Every lifecycle event appends a row inside the transition that causes it
(`match_found`, `settled`, `refund`, `challenge_received`, `challenge_accepted`,
`friend_request`, `room_filled`, `system` — 08-phase-5 · deliverable 7); the
Inbox (`GET /notifications`) consumes them and marks them read. Flushes, never
commits — the caller owns the transaction boundary.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import Notification
from . import email_service, push_service

log = structlog.get_logger(__name__)

_DEFAULT_LIMIT = 50

# Postgres LISTEN/NOTIFY channel the SSE stream (`routers/events.py`) subscribes
# to. Every emit publishes here so a connected client refreshes the instant the
# event's transaction commits — the notify is queued now and delivered by
# Postgres on COMMIT, so a rolled-back transition never pushes a phantom event.
_EVENTS_CHANNEL = "moneymatch_events"

# Copy for the browser push, per kind → (title, body, deep-link). Kinds absent
# here (refund / system) stay in-app only.
_PUSH_COPY: dict[str, tuple[str, str, str]] = {
    "match_found": (
        "Match found",
        "Your opponent is ready — confirm to play.",
        "/play",
    ),
    "settled": ("Contest settled", "Your result is in.", "/activity"),
    "room_filled": (
        "Your pool is full",
        "Play your next match to lock in your score.",
        "/pools",
    ),
    "dispute_resolved": (
        "Dispute update",
        "There's an update on a contest you disputed.",
        "/activity",
    ),
    "challenge_received": (
        "New challenge",
        "Someone challenged you to a match.",
        "/social?tab=inbox",
    ),
    "challenge_accepted": (
        "Challenge accepted",
        "Your challenge was accepted — jump in.",
        "/play",
    ),
    "friend_request": ("Friend request", "You have a new friend request.", "/social"),
}

# A deliberately small subset of kinds also gets a transactional email — the
# high-value, non-time-critical nudges worth reaching an inbox for. (subject,
# body); the deep link reuses the matching `_PUSH_COPY` path. Anything absent
# here stays in-app + push only, so email never becomes a firehose. Only real
# addresses receive it — see `email_service` (username accounts are skipped).
_EMAIL_COPY: dict[str, tuple[str, str]] = {
    "match_found": (
        "Your match is ready",
        "Your opponent is ready — confirm to play your match.",
    ),
    "settled": (
        "Your contest settled",
        "Your result is in. Open Money Match to see how it went.",
    ),
    "challenge_received": (
        "You've been challenged",
        "Someone challenged you to a match on Money Match.",
    ),
}


async def emit(
    session: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
) -> Notification:
    """Append one notification row for a user, and best-effort browser push."""
    row = Notification(user_id=user_id, kind=kind, payload=payload)
    session.add(row)
    await session.flush()

    # Publish a lightweight event on the LISTEN/NOTIFY channel (delivered at
    # commit). The client only needs "something changed for you" to refetch, so
    # the payload is just the recipient + kind — never money, never PII.
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {
            "channel": _EVENTS_CHANNEL,
            "payload": json.dumps({"user_id": str(user_id), "kind": kind}),
        },
    )

    copy = _PUSH_COPY.get(kind)
    if copy is not None:
        try:
            await push_service.send_to_user(
                session, user_id, title=copy[0], body=copy[1], url=copy[2]
            )
        except Exception as exc:  # noqa: BLE001 — push must never break the caller
            log.warning("push.emit_failed", kind=kind, error=str(exc))

    email_copy = _EMAIL_COPY.get(kind)
    if email_copy is not None:
        try:
            subject, body = email_copy
            link_path = copy[2] if copy is not None else None
            await email_service.send_to_user(
                session, user_id, subject=subject, body=body, link_path=link_path
            )
        except Exception as exc:  # noqa: BLE001 — email must never break the caller
            log.warning("email.emit_failed", kind=kind, error=str(exc))
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
