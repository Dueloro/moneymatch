"""Transactional email seam (Resend)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from moneymatch_api.config import get_settings
from moneymatch_api.models.user import User, gen_friend_code
from moneymatch_api.services import email_service


@pytest.mark.nodb
def test_is_deliverable_filters_synthetic_addresses():
    assert email_service.is_deliverable("player@example.com") is True
    assert email_service.is_deliverable("kvem_@users.moneymatch.app") is False
    assert email_service.is_deliverable(None) is False


@pytest.mark.nodb
def test_is_enabled_is_false_without_key():
    assert email_service.is_enabled() is False


async def _make_user(session, *, email: str) -> User:
    user = User(auth_id=f"auth|{email}", email=email, friend_code=gen_friend_code())
    session.add(user)
    await session.flush()
    return user


async def test_send_is_noop_without_key(session):
    user = await _make_user(session, email="real@example.com")
    sent = await email_service.send_to_user(session, user.id, subject="Hi", body="Body")
    assert sent is False


async def test_send_skips_synthetic_address(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    user = await _make_user(session, email="kvem_@users.moneymatch.app")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT)
        sent = await email_service.send_to_user(
            session, user.id, subject="Hi", body="Body"
        )
    assert sent is False
    assert not route.called


async def test_send_posts_to_resend_for_real_address(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "email_from", "Money Match <noreply@moneymatch.app>")
    monkeypatch.setattr(settings, "web_origin", "https://app.moneymatch.app")
    user = await _make_user(session, email="real@example.com")

    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "email_1"})
        )
        sent = await email_service.send_to_user(
            session,
            user.id,
            subject="Your contest settled",
            body="Your result is in.",
            link_path="/activity",
        )

    assert sent is True
    assert route.called
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer re_test_key"
    payload = json.loads(req.content)
    assert payload["from"] == "Money Match <noreply@moneymatch.app>"
    assert payload["to"] == ["real@example.com"]
    assert payload["subject"] == "Your contest settled"
    assert "https://app.moneymatch.app/activity" in payload["text"]
    assert "https://app.moneymatch.app/activity" in payload["html"]


async def test_send_swallows_provider_error(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    user = await _make_user(session, email="real@example.com")
    with respx.mock:
        respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(422, json={"message": "bad from"})
        )
        sent = await email_service.send_to_user(
            session, user.id, subject="Hi", body="Body"
        )
    assert sent is False


async def test_html_uses_hybrid_brand(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "web_origin", "https://moneymatch-beta.vercel.app")
    user = await _make_user(session, email="real@example.com")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "e1"})
        )
        await email_service.send_to_user(
            session,
            user.id,
            subject="Your contest settled",
            body="Your result is in.",
            link_path="/activity",
        )
    html = json.loads(route.calls.last.request.content)["html"]
    assert "/email/logo.png" in html
    assert "Open Money Match" in html
    assert "Dueloro" in html
