"""Resend inbound-email primitives for support-thread replies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any

import httpx

from ..config import get_settings

_RECEIVING_ENDPOINT = "https://api.resend.com/emails/receiving"
_REPLY_LOCAL = re.compile(
    r"^support-(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
    re.IGNORECASE,
)
_QUOTED_REPLY = re.compile(
    r"\n(?:On .+ wrote:|From:.+|-----Original Message-----)\s*\n",
    re.IGNORECASE | re.DOTALL,
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def email_address(value: str | None) -> str:
    return parseaddr(value or "")[1].strip().lower()


def reply_address(conversation_id: uuid.UUID) -> str:
    domain = get_settings().support_inbound_domain.strip().lower()
    return f"support-{conversation_id}@{domain}"


def conversation_from_recipients(recipients: list[str]) -> uuid.UUID | None:
    domain = get_settings().support_inbound_domain.strip().lower()
    for recipient in recipients:
        address = email_address(recipient)
        local, separator, recipient_domain = address.rpartition("@")
        if not separator or recipient_domain != domain:
            continue
        match = _REPLY_LOCAL.fullmatch(local)
        if match:
            return uuid.UUID(match.group("id"))
    return None


def verify_webhook(
    payload: bytes,
    *,
    webhook_id: str,
    timestamp: str,
    signature: str,
    secret: str,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify Resend's Svix signature against the untouched request body."""
    if not all((payload, webhook_id, timestamp, signature, secret)):
        raise ValueError("missing webhook signature data")
    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise ValueError("invalid webhook timestamp") from exc
    if abs((now or int(time.time())) - sent_at) > 300:
        raise ValueError("webhook timestamp is outside the tolerance window")
    encoded_secret = secret.removeprefix("whsec_")
    try:
        key = base64.b64decode(encoded_secret, validate=True)
    except ValueError as exc:
        raise ValueError("invalid webhook secret") from exc
    signed = f"{webhook_id}.{timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    candidates = [part.split(",", 1)[1] for part in signature.split() if "," in part]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise ValueError("invalid webhook signature")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("invalid webhook payload")
    return value


async def retrieve_received_email(email_id: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{_RECEIVING_ENDPOINT}/{email_id}",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        )
        response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError("Resend returned an invalid received email")
    return value


def reply_text(received: dict[str, Any]) -> str:
    raw = received.get("text")
    if not isinstance(raw, str) or not raw.strip():
        html = received.get("html")
        if not isinstance(html, str):
            return ""
        parser = _TextExtractor()
        parser.feed(html)
        raw = " ".join(parser.parts)
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = _QUOTED_REPLY.split(text, maxsplit=1)[0].strip()
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()
