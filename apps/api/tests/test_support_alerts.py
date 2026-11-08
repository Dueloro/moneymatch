"""Support messages alert SUPPORT_EMAIL via Resend: after commit, best-effort, and
at most one email per thread per window (later lines are batched).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from moneymatch_api.config import get_settings
from moneymatch_api.services import chat_service, email_service, support_alerts

from .conftest import auth_headers
from .test_chat import _befriend, _onboard

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


@pytest.fixture(autouse=True)
def _resend(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "support_email", "support@dueloro.com")
    monkeypatch.setattr(support_alerts, "WINDOW_SECONDS", 0.05)
    yield
    support_alerts.reset()


async def _support_thread(client, auth: str) -> str:
    r = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers(auth),
        json={"kind": "support"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _say(client, auth: str, conversation_id: str, text: str) -> None:
    r = await client.post(
        f"{V1}/chat/conversations/{conversation_id}/messages",
        headers=auth_headers(auth),
        json={"body": text},
    )
    assert r.status_code == 200, r.text


async def test_user_message_emails_support_once(client):
    user_id = await _onboard(client, "auth_a", "alice")
    conversation_id = await _support_thread(client, "auth_a")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "e1"})
        )
        await _say(client, "auth_a", conversation_id, "my payout is stuck\x07")
        await support_alerts.drain()

    assert route.call_count == 1
    payload = json.loads(route.calls.last.request.content)
    assert payload["to"] == ["support@dueloro.com"]
    assert payload["subject"] == "Support: alice"
    assert payload["reply_to"] == "player@example.com"
    assert "html" not in payload
    text = payload["text"]
    assert "my payout is stuck" in text and "\x07" not in text
    assert user_id in text and conversation_id in text and "UTC" in text
    assert chat_service.SUPPORT_AUTO_REPLY not in text
    assert chat_service.SUPPORT_GREETING not in text


async def test_dm_does_not_email(client):
    alice = await _onboard(client, "auth_a", "alice")
    await _onboard(client, "auth_b", "bob")
    await _befriend(client, "auth_a", "auth_b", "bob")
    r = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers("auth_b"),
        json={"kind": "dm", "user_id": alice},
    )
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT)
        await _say(client, "auth_b", r.json()["id"], "gg")
        await support_alerts.drain()
    assert not route.called


async def test_resend_failure_does_not_fail_the_request(client):
    await _onboard(client, "auth_a", "alice")
    conversation_id = await _support_thread(client, "auth_a")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            side_effect=httpx.ConnectError("down")
        )
        await _say(client, "auth_a", conversation_id, "hello?")
        await support_alerts.drain()
    assert route.called


async def test_rate_limit_batches_a_burst(client, monkeypatch):
    monkeypatch.setattr(support_alerts, "WINDOW_SECONDS", 0.5)
    await _onboard(client, "auth_a", "alice")
    conversation_id = await _support_thread(client, "auth_a")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "e1"})
        )
        for line in ("one", "two", "three"):
            await _say(client, "auth_a", conversation_id, line)
        assert route.call_count == 1
        await support_alerts.drain()

    assert route.call_count == 2
    first, second = (json.loads(c.request.content)["text"] for c in route.calls)
    assert "one" in first and "two" not in first
    assert "two" in second and "three" in second and "2 messages" in second


async def test_long_message_is_truncated(client, monkeypatch):
    monkeypatch.setattr(support_alerts, "MAX_LINE_CHARS", 50)
    await _onboard(client, "auth_a", "alice")
    conversation_id = await _support_thread(client, "auth_a")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "e1"})
        )
        await _say(client, "auth_a", conversation_id, "x" * 500)
        await support_alerts.drain()
    text = json.loads(route.calls.last.request.content)["text"]
    assert "x" * 50 in text and "x" * 51 not in text and "[truncated]" in text


async def test_noop_without_resend(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", None)
    await _onboard(client, "auth_a", "alice")
    conversation_id = await _support_thread(client, "auth_a")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT)
        await _say(client, "auth_a", conversation_id, "hi")
        await support_alerts.drain()
    assert not route.called
