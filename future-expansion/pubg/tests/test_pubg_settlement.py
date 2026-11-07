"""PUBG settlement resilience: a host outage / rate-limit during the poll must
surface as PENDING(host_error) so the worker EXTENDS the window, never as a
silent "no qualifying game" that consumes it. No DB — grade() only reads attrs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import respx

from moneymatch_api.config import get_settings
from moneymatch_api.services import grading
from moneymatch_api.services.hosts import pubg

SHARD = "https://api.pubg.com/shards/steam"


@pytest.fixture
def pubg_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "pubg_api_key", "test-key")
    pubg.clear_match_cache()
    yield
    pubg.clear_match_cache()


def _match_obj():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        game="pubg.steam",
        market="win_next",
        matched_at=now - timedelta(hours=1),
        window_ends_at=now + timedelta(hours=23),
    )


def _seats():
    return [
        SimpleNamespace(user_id=uuid.uuid4(), host_account_id="account.a"),
        SimpleNamespace(user_id=uuid.uuid4(), host_account_id="account.b"),
    ]


@respx.mock
async def test_outage_during_poll_yields_host_error(pubg_key):
    respx.get(f"{SHARD}/players/account.a").mock(return_value=httpx.Response(503))
    outcome = await grading.grade(_match_obj(), _seats(), datetime.now(UTC))
    assert outcome.status == grading.PENDING
    assert outcome.host_error is True


@respx.mock
async def test_rate_limit_during_poll_yields_host_error(pubg_key):
    respx.get(f"{SHARD}/players/account.a").mock(return_value=httpx.Response(429))
    outcome = await grading.grade(_match_obj(), _seats(), datetime.now(UTC))
    assert outcome.status == grading.PENDING
    assert outcome.host_error is True
