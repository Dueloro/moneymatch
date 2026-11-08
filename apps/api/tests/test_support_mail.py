from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid

import pytest

from moneymatch_api.services import support_mail

pytestmark = pytest.mark.nodb


def test_reply_address_round_trip(monkeypatch):
    conversation_id = uuid.uuid4()
    monkeypatch.setattr(
        support_mail.get_settings(), "support_inbound_domain", "reply.dueloro.com"
    )
    address = support_mail.reply_address(conversation_id)
    assert address == f"support-{conversation_id}@reply.dueloro.com"
    assert support_mail.conversation_from_recipients([address]) == conversation_id
    assert support_mail.conversation_from_recipients(["other@example.com"]) is None


def test_verify_webhook_accepts_the_raw_body():
    payload = json.dumps(
        {"type": "email.received", "data": {"email_id": "e1"}}
    ).encode()
    webhook_id = "msg_1"
    timestamp = "1000"
    secret_bytes = b"test webhook secret"
    secret = f"whsec_{base64.b64encode(secret_bytes).decode()}"
    signed = f"{webhook_id}.{timestamp}.".encode() + payload
    signature = base64.b64encode(
        hmac.new(secret_bytes, signed, hashlib.sha256).digest()
    ).decode()
    event = support_mail.verify_webhook(
        payload,
        webhook_id=webhook_id,
        timestamp=timestamp,
        signature=f"v1,{signature}",
        secret=secret,
        now=1000,
    )
    assert event["data"]["email_id"] == "e1"


def test_verify_webhook_rejects_a_bad_signature():
    with pytest.raises(ValueError, match="signature"):
        support_mail.verify_webhook(
            b"{}",
            webhook_id="msg_1",
            timestamp="1000",
            signature="v1,bad",
            secret=f"whsec_{base64.b64encode(b'secret').decode()}",
            now=1000,
        )


def test_reply_text_removes_the_quoted_thread():
    text = support_mail.reply_text(
        {
            "text": (
                "I can help with that.\n\nOn Monday, Player wrote:\n> My match is stuck"
            )
        }
    )
    assert text == "I can help with that."
