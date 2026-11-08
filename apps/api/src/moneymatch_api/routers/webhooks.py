"""Signed third-party webhooks."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.session import get_session
from ..errors import APIError
from ..models.chat import MAX_MESSAGE_CHARS
from ..services import (
    admin_support_service,
    email_service,
    support_alerts,
    support_mail,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger(__name__)


@router.post("/resend")
async def resend_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.resend_webhook_secret or not settings.resend_api_key:
        raise APIError(
            "webhook_not_configured",
            "The Resend webhook is not configured.",
            status_code=503,
        )
    raw = await request.body()
    try:
        event = support_mail.verify_webhook(
            raw,
            webhook_id=request.headers.get("svix-id", ""),
            timestamp=request.headers.get("svix-timestamp", ""),
            signature=request.headers.get("svix-signature", ""),
            secret=settings.resend_webhook_secret,
        )
    except (ValueError, TypeError) as exc:
        raise APIError(
            "invalid_webhook", "Invalid webhook signature.", status_code=400
        ) from exc
    if event.get("type") != "email.received":
        return {"ok": True, "ignored": True}
    data = event.get("data")
    email_id = data.get("email_id") if isinstance(data, dict) else None
    if not isinstance(email_id, str) or not email_id:
        raise APIError("invalid_webhook", "Missing received email id.", status_code=400)
    if await admin_support_service.has_resend_email(session, email_id):
        return {"ok": True, "duplicate": True}

    try:
        received = await support_mail.retrieve_received_email(email_id)
    except Exception as exc:  # Resend retries a non-2xx delivery.
        log.warning("support.inbound_fetch_failed", email_id=email_id, error=str(exc))
        raise APIError(
            "inbound_email_unavailable",
            "The received email could not be loaded yet.",
            status_code=503,
        ) from exc
    recipients: list[str] = []
    for key in ("to", "received_for"):
        value = received.get(key)
        if isinstance(value, str):
            recipients.append(value)
        elif isinstance(value, list):
            recipients.extend(item for item in value if isinstance(item, str))
    conversation_id = support_mail.conversation_from_recipients(recipients)
    if conversation_id is None:
        return {"ok": True, "ignored": True}
    try:
        user, _ = await admin_support_service.get_thread(session, conversation_id)
    except APIError as exc:
        if exc.code == "support_thread_not_found":
            return {"ok": True, "ignored": True}
        raise
    sender = support_mail.email_address(received.get("from"))
    support_sender = support_mail.email_address(settings.support_email)
    user_sender = support_mail.email_address(user.email)
    if sender not in {support_sender, user_sender}:
        log.warning(
            "support.inbound_sender_rejected",
            conversation_id=str(conversation_id),
            sender=sender,
        )
        return {"ok": True, "ignored": True}
    text = support_mail.reply_text(received)
    if not text:
        return {"ok": True, "ignored": True}
    if len(text) > MAX_MESSAGE_CHARS:
        text = f"{text[: MAX_MESSAGE_CHARS - 14]}\n… [truncated]"
    from_support = sender == support_sender
    payload = {
        "source": "email",
        "resend_email_id": email_id,
        "message_id": str(received.get("message_id") or ""),
    }
    await admin_support_service.append_reply(
        session,
        conversation_id,
        text,
        sender_id=None if from_support else user.id,
        payload=payload,
    )
    await session.commit()
    if from_support:
        await email_service.send_to_user(
            session,
            user.id,
            subject="Dueloro Support replied",
            body=text,
            link_path="/social?tab=inbox",
            reply_to=support_mail.reply_address(conversation_id),
        )
    else:
        support_alerts.notify(user, conversation_id, text)
    return {"ok": True}
