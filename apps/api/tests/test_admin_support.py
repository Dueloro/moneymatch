from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest
import respx
from sqlalchemy import func, select

from moneymatch_api.config import get_settings
from moneymatch_api.models.admin_audit import AdminAudit
from moneymatch_api.models.user import User
from moneymatch_api.services import email_service, support_mail

from .conftest import auth_headers, new_sessionmaker
from .test_chat import _onboard

pytestmark = pytest.mark.asyncio
V1 = "/api/v1"


async def _admin(client):
    await client.get(f"{V1}/me", headers=auth_headers("support_admin"))
    async with new_sessionmaker()() as session:
        admin = await session.scalar(
            select(User).where(User.auth_id == "support_admin")
        )
        admin.username = "admin"
        admin.role = "admin"
        await session.commit()


async def _support_thread(client) -> str:
    await _onboard(client, "support_user", "alice")
    response = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers("support_user"),
        json={"kind": "support"},
    )
    conversation_id = response.json()["id"]
    await client.post(
        f"{V1}/chat/conversations/{conversation_id}/messages",
        headers=auth_headers("support_user"),
        json={"body": "My match is stuck"},
    )
    return conversation_id


async def test_admin_lists_and_replies_to_a_support_thread(client, monkeypatch):
    settings = get_settings()
    await _admin(client)
    conversation_id = await _support_thread(client)
    monkeypatch.setattr(settings, "resend_api_key", "re_test")

    response = await client.get(
        f"{V1}/admin/support", headers=auth_headers("support_admin")
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["conversation_id"] == conversation_id
    assert response.json()[0]["awaiting_reply"] is True

    with respx.mock:
        sent = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "sent_1"})
        )
        response = await client.post(
            f"{V1}/admin/support/{conversation_id}/reply",
            headers=auth_headers("support_admin"),
            json={"body": "We found it and settlement is running."},
        )
    assert response.status_code == 200, response.text
    assert response.json()["messages"][-1]["sender"] == "support"
    payload = json.loads(sent.calls.last.request.content)
    assert payload["to"] == ["player@example.com"]
    assert payload["reply_to"] == f"support-{conversation_id}@reply.dueloro.com"

    user_thread = await client.get(
        f"{V1}/chat/conversations/{conversation_id}",
        headers=auth_headers("support_user"),
    )
    assert user_thread.json()["messages"][-1]["body"].startswith("We found it")
    async with new_sessionmaker()() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AdminAudit)
            .where(AdminAudit.action == "support.reply")
        )
    assert count == 1


def _signed_headers(payload: bytes, secret: str) -> dict[str, str]:
    webhook_id = "msg_1"
    timestamp = str(int(time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{webhook_id}.{timestamp}.".encode() + payload
    signature = base64.b64encode(
        hmac.new(key, signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": webhook_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
        "content-type": "application/json",
    }


async def test_staff_email_reply_is_added_to_the_thread(client, monkeypatch):
    settings = get_settings()
    secret = f"whsec_{base64.b64encode(b'test webhook secret').decode()}"
    conversation_id = await _support_thread(client)
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(settings, "resend_webhook_secret", secret)
    monkeypatch.setattr(settings, "support_email", "support@dueloro.com")
    event = {"type": "email.received", "data": {"email_id": "received_1"}}
    raw = json.dumps(event).encode()
    received = {
        "id": "received_1",
        "from": "Dueloro Support <support@dueloro.com>",
        "to": [f"support-{conversation_id}@reply.dueloro.com"],
        "received_for": [],
        "message_id": "<reply-1@example.com>",
        "text": "Thanks—we fixed this.\n\nOn Sunday, alice wrote:\n> My match is stuck",
    }
    with respx.mock:
        respx.get(f"{support_mail._RECEIVING_ENDPOINT}/received_1").mock(
            return_value=httpx.Response(200, json=received)
        )
        sent = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "sent_2"})
        )
        response = await client.post(
            f"{V1}/webhooks/resend",
            content=raw,
            headers=_signed_headers(raw, secret),
        )
    assert response.status_code == 200, response.text
    assert sent.called
    thread = await client.get(
        f"{V1}/chat/conversations/{conversation_id}",
        headers=auth_headers("support_user"),
    )
    assert thread.json()["messages"][-1]["body"] == "Thanks—we fixed this."

    duplicate = await client.post(
        f"{V1}/webhooks/resend",
        content=raw,
        headers=_signed_headers(raw, secret),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
