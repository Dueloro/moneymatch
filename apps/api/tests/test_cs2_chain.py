"""Valve's share-code chain: the status codes are the whole contract.

`GetNextMatchSharingCode` says four different things with four different HTTP
statuses, and they demand four different actions. Treating any of them as
"failed" is how you either stop collecting a player's matches silently, or hold
a retry loop open against a request that can never succeed.

The last one is not hypothetical: Valve temporarily blocks an API key that
keeps presenting bad auth codes. One player's stale cursor, retried, takes
settlement down for everyone.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from moneymatch_api.services import cs2_chain
from moneymatch_api.services.hosts import steam
from moneymatch_api.services.hosts.errors import HostError, HostUnavailable

pytestmark = pytest.mark.nodb

NEXT = "CSGO-abcde-fghij-klmno-pqrst-uvwxy"


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


def _call(monkeypatch, outcome):
    """Run `get_next_share_code` with a stubbed transport."""

    async def fake_request(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(steam, "request_json", fake_request)
    monkeypatch.setattr(steam, "_api_key", lambda: "test-key")
    return asyncio.run(
        steam.get_next_share_code("76561198748110372", "AAAA-BBBB", "CSGO-x")
    )


# --------------------------------------------------------------------------- #
# The happy path and the one that looks like failure but is not.
# --------------------------------------------------------------------------- #


def test_a_new_match_returns_its_share_code(monkeypatch):
    got = _call(monkeypatch, _Response(200, {"result": {"nextcode": NEXT}}))
    assert got == NEXT


def test_caught_up_is_not_an_error(monkeypatch):
    """202 means the player has not played since. The common case."""
    assert _call(monkeypatch, _Response(202)) is None


def test_valve_saying_n_a_is_also_caught_up(monkeypatch):
    """Some responses answer 200 with a placeholder instead of 202."""
    assert _call(monkeypatch, _Response(200, {"result": {"nextcode": "n/a"}})) is None


def test_an_empty_result_is_caught_up_not_a_crash(monkeypatch):
    assert _call(monkeypatch, _Response(200, {"result": {}})) is None


# --------------------------------------------------------------------------- #
# The failures, which are not interchangeable.
# --------------------------------------------------------------------------- #


def test_a_cursor_from_someone_elses_match_stops_the_chain(monkeypatch):
    """412. Retrying this can never work, so it must never be retried."""
    with pytest.raises(steam.ChainError) as exc:
        _call(monkeypatch, HostError("steam", "412", 412))
    assert exc.value.code == "chain_cursor_not_yours"
    assert exc.value.retryable is False


def test_a_rejected_auth_code_stops_the_chain(monkeypatch):
    """403. Repeated bad auth codes get the API key blocked for everyone."""
    with pytest.raises(steam.ChainError) as exc:
        _call(monkeypatch, HostError("steam", "403", 403))
    assert exc.value.code == "chain_auth_code_rejected"
    assert exc.value.retryable is False


def test_rate_limiting_is_retryable(monkeypatch):
    """429 is Valve asking for patience, not a broken link."""
    with pytest.raises(steam.ChainError) as exc:
        _call(monkeypatch, HostError("steam", "429", 429))
    assert exc.value.retryable is True


def test_steam_being_down_is_retryable(monkeypatch):
    with pytest.raises(steam.ChainError) as exc:
        _call(monkeypatch, HostUnavailable("steam", "503", 503))
    assert exc.value.retryable is True


def test_the_two_permanent_failures_are_told_apart(monkeypatch):
    """They need different fixes, so they cannot share a message."""
    with pytest.raises(steam.ChainError) as cursor:
        _call(monkeypatch, HostError("steam", "412", 412))
    with pytest.raises(steam.ChainError) as auth:
        _call(monkeypatch, HostError("steam", "403", 403))
    assert cursor.value.code != auth.value.code
    assert str(cursor.value) != str(auth.value)


# --------------------------------------------------------------------------- #
# The status code has to survive the trip, or none of the above can work.
# --------------------------------------------------------------------------- #


def test_a_host_error_carries_its_status():
    """Recovering it by parsing the message would decide money by substring."""
    assert HostError("steam", "boom", 412).status_code == 412


def test_a_host_error_without_a_status_is_still_valid():
    assert HostError("steam", "boom").status_code is None


# --------------------------------------------------------------------------- #
# The cursor must not step over a match the sidecar merely could not fetch.
# --------------------------------------------------------------------------- #


class _Chain:
    """Enough of a chain row for the walk."""

    def __init__(self, cursor: str) -> None:
        self.user_id = uuid.uuid4()
        self.steam_id = "76561198748110372"
        self.auth_code = "AAAA-BBBB"
        self.known_code = cursor
        self.state = "active"
        self.last_error = None
        self.last_polled_at = None
        self.last_code_at = None

    def is_active(self) -> bool:
        return self.state == "active"


class _Session:
    async def flush(self):
        return None


def _walk(monkeypatch, resolve_error):
    """Run one sync where Valve offers exactly one new code."""
    chain = _Chain("CSGO-old")
    codes = iter(["CSGO-new", None])

    async def fake_next(*args, **kwargs):
        return next(codes)

    async def fake_get_by_share_code(*args, **kwargs):
        return None

    async def fake_resolve(code):
        raise resolve_error

    monkeypatch.setattr(steam, "get_next_share_code", fake_next)
    monkeypatch.setattr(
        cs2_chain.cs2_matches, "get_by_share_code", fake_get_by_share_code
    )
    monkeypatch.setattr(cs2_chain.gc_client, "resolve", fake_resolve)
    asyncio.run(cs2_chain.sync(_Session(), chain))
    return chain


def test_a_sidecar_outage_does_not_skip_the_match(monkeypatch):
    """The bug this exists for: a real match, dropped because the fetcher blinked.

    The player staked money and played the game. Losing the result because the
    Game Coordinator was restarting is, from their side, the product not working.
    """
    chain = _walk(monkeypatch, cs2_chain.gc_client.GcError("gc down", retryable=True))
    assert chain.known_code == "CSGO-old"


def test_a_code_the_gc_will_never_know_does_not_wedge_the_chain(monkeypatch):
    """The opposite failure: one dead code must not block every later match."""
    chain = _walk(monkeypatch, cs2_chain.gc_client.GcError("unknown", retryable=False))
    assert chain.known_code == "CSGO-new"


def test_an_outage_leaves_the_chain_healthy(monkeypatch):
    """It is not the player's fault and needs no reconnecting."""
    chain = _walk(monkeypatch, cs2_chain.gc_client.GcError("gc down", retryable=True))
    assert chain.state == "active"
    assert chain.last_error is None
