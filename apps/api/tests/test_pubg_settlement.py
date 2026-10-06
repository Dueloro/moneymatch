"""PUBG settlement resilience, now that PUBG results come from stored history.

Grading never calls the PUBG API; the background ingester does. So the two
failure modes to guard are:

- the **grader** reading stale stored history: an account the ingester has not
  polled lately must grade as PENDING(host_error), which extends the window,
  never as "no qualifying game" (a forfeit or a cancel off missing data);
- the **ingester** hitting an outage / rate limit: the poll fails, the account
  is marked as attempted (so it does not hog the queue) but not as polled, and
  nothing is stored.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import respx

from moneymatch_api.config import get_settings
from moneymatch_api.db.session import get_sessionmaker
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.services import grading, match_ingestion
from moneymatch_api.services.hosts import pubg

from .factories import create_user

pytestmark = pytest.mark.asyncio

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


async def _link(session, account: str, *, polled_at=None) -> LinkedAccount:
    user = await create_user(session, username=account.replace(".", "_"))
    link = LinkedAccount(
        user_id=user.id,
        game="pubg.steam",
        host_account_id=account,
        host_username=account,
        ingest_polled_at=polled_at,
    )
    session.add(link)
    await session.commit()
    return link


def _seat(link: LinkedAccount):
    return SimpleNamespace(
        user_id=link.user_id,
        host_account_id=link.host_account_id,
        linked_account_id=link.id,
    )


async def test_unpolled_history_grades_as_host_error(session):
    a = await _link(session, "account.a")  # never polled
    b = await _link(session, "account.b", polled_at=datetime.now(UTC))
    outcome = await grading.grade(_match_obj(), [_seat(a), _seat(b)], datetime.now(UTC))
    assert outcome.status == grading.PENDING
    assert outcome.host_error is True


async def test_stale_history_grades_as_host_error(session):
    old = datetime.now(UTC) - timedelta(hours=2)
    a = await _link(session, "account.a", polled_at=old)
    b = await _link(session, "account.b", polled_at=old)
    outcome = await grading.grade(_match_obj(), [_seat(a), _seat(b)], datetime.now(UTC))
    assert outcome.status == grading.PENDING
    assert outcome.host_error is True


async def test_fresh_history_with_no_games_is_just_waiting(session):
    now = datetime.now(UTC)
    a = await _link(session, "account.a", polled_at=now)
    b = await _link(session, "account.b", polled_at=now)
    outcome = await grading.grade(_match_obj(), [_seat(a), _seat(b)], now)
    assert outcome.status == grading.PENDING
    assert outcome.host_error is False


@pytest.mark.parametrize("status", [503, 429])
@respx.mock
async def test_ingest_outage_marks_attempt_not_poll(session, pubg_key, status):
    link = await _link(session, "account.a")
    respx.get(f"{SHARD}/players/account.a").mock(return_value=httpx.Response(status))

    await match_ingestion.run_cycle(get_sessionmaker())

    await session.refresh(link)
    assert link.ingest_attempted_at is not None
    assert link.ingest_polled_at is None  # a failure is never "nothing new"


async def test_a_missing_api_key_is_a_failed_poll_not_an_empty_one(
    session, monkeypatch
):
    """No key must never look like "this player played nothing"."""
    monkeypatch.setattr(get_settings(), "pubg_api_key", None)
    link = await _link(session, "account.nokey")
    await match_ingestion.run_cycle(get_sessionmaker())
    await session.refresh(link)
    assert link.ingest_attempted_at is not None
    assert link.ingest_polled_at is None
