"""Web Push delivery (VAPID) — the browser-push side of notifications.

Subscriptions are stored per browser endpoint; `send_to_user` fans a payload out
to all of a user's subscriptions. `pywebpush` is synchronous, so each send runs
in a worker thread to keep the event loop free. A push service that returns
404/410 means the subscription is dead, so we prune it. Without a VAPID keypair
configured, push is a no-op and the app falls back to in-app notifications.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.push import PushSubscription

log = structlog.get_logger(__name__)


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.vapid_private_key and s.vapid_public_key)


def public_key() -> str | None:
    return get_settings().vapid_public_key


async def subscribe(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> PushSubscription:
    """Upsert a browser subscription (an endpoint is globally unique)."""
    existing = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    if existing is not None:
        existing.user_id = user_id
        existing.p256dh = p256dh
        existing.auth = auth
        await session.flush()
        return existing
    sub = PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
    session.add(sub)
    await session.flush()
    return sub


async def unsubscribe(session: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
    )


def _send_one(sub_info: dict[str, Any], data: str) -> None:
    """Blocking single push (run in a thread). Raises on failure."""
    from pywebpush import webpush

    s = get_settings()
    webpush(
        subscription_info=sub_info,
        data=data,
        vapid_private_key=s.vapid_private_key,
        vapid_claims={"sub": s.vapid_subject},
        timeout=10,
    )


async def send_to_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    body: str,
    url: str | None = None,
) -> int:
    """Best-effort push to every subscription of `user_id`. Returns the count
    delivered; prunes dead subscriptions. Never raises."""
    if not is_enabled():
        return 0
    subs = list(
        await session.scalars(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )
    )
    if not subs:
        return 0

    data = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    dead: list[str] = []
    for sub in subs:
        info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            await asyncio.to_thread(_send_one, info, data)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — best-effort; classify by status
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                dead.append(sub.endpoint)
            else:
                log.warning("push.send_failed", error=str(exc), status=status)
    if dead:
        await session.execute(
            delete(PushSubscription).where(PushSubscription.endpoint.in_(dead))
        )
    return sent
