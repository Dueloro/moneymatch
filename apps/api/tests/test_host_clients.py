"""Host-client resilience: typed errors, retries, and fail-soft polls.

All host APIs are respx-mocked — no live network (05-phase-2 · CI green with zero
network access). Covers the failure-mode rows the phase requires: 5xx → typed
error, 404 → not-found, timeout path, and the fail-soft history polls.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from moneymatch_api.config import get_settings
from moneymatch_api.services.hosts import faceit, lichess, opendota
from moneymatch_api.services.hosts._client import request_json
from moneymatch_api.services.hosts.errors import HostNotFound, HostUnavailable


@pytest.fixture
def faceit_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "faceit_api_key", "test-key")
    faceit.clear_match_cache()
    yield
    faceit.clear_match_cache()


URL = "https://example.test/x"


@respx.mock
async def test_request_json_404_raises_not_found():
    respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(HostNotFound):
        await request_json("example", "GET", URL)


@respx.mock
async def test_request_json_5xx_retries_then_unavailable():
    route = respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(HostUnavailable):
        await request_json("example", "GET", URL)
    assert route.call_count == 3  # 1 try + 2 retries


@respx.mock
async def test_request_json_retries_recover():
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": True})]
    )
    response = await request_json("example", "GET", URL)
    assert response.json() == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_request_json_timeout_is_unavailable():
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(HostUnavailable):
        await request_json("example", "GET", URL)


# --------------------------------------------------------------------------- #
# Lichess
# --------------------------------------------------------------------------- #


@respx.mock
async def test_lichess_get_user_ok_and_missing():
    respx.get("https://lichess.org/api/user/magnus").mock(
        return_value=httpx.Response(200, json={"username": "Magnus", "id": "magnus"})
    )
    assert (await lichess.get_user("magnus"))["username"] == "Magnus"

    respx.get("https://lichess.org/api/user/ghost").mock(
        return_value=httpx.Response(404)
    )
    assert await lichess.get_user("ghost") is None  # 404 → None, not an error


@respx.mock
async def test_lichess_get_user_closed_account_is_none():
    respx.get("https://lichess.org/api/user/gone").mock(
        return_value=httpx.Response(200, json={"id": "gone", "closed": True})
    )
    assert await lichess.get_user("gone") is None


@respx.mock
async def test_lichess_games_fail_soft_on_outage():
    respx.get(url__regex=r"https://lichess\.org/api/games/user/.*").mock(
        return_value=httpx.Response(500)
    )
    assert await lichess.get_user_games("magnus", 0) == []


# --------------------------------------------------------------------------- #
# FaceIt
# --------------------------------------------------------------------------- #


async def test_faceit_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(get_settings(), "faceit_api_key", None)
    assert await faceit.get_player("ZywOo") is None


@respx.mock
async def test_faceit_get_player_ok(faceit_key):
    respx.get("https://open.faceit.com/data/v4/players").mock(
        return_value=httpx.Response(200, json={"player_id": "abc", "nickname": "ZywOo"})
    )
    player = await faceit.get_player("ZywOo")
    assert player["nickname"] == "ZywOo"


@respx.mock
async def test_faceit_match_stats_ttl_cached(faceit_key):
    route = respx.get("https://open.faceit.com/data/v4/matches/m1/stats").mock(
        return_value=httpx.Response(200, json={"rounds": []})
    )
    first = await faceit.get_match_stats("m1")
    second = await faceit.get_match_stats("m1")
    assert first == second == {"rounds": []}
    assert route.call_count == 1  # second read served from cache


# --------------------------------------------------------------------------- #
# OpenDota
# --------------------------------------------------------------------------- #


@respx.mock
async def test_opendota_private_profile_is_none():
    respx.get("https://api.opendota.com/api/players/123").mock(
        return_value=httpx.Response(200, json={"profile": None})
    )
    assert await opendota.get_player("123") is None


@respx.mock
async def test_opendota_recent_matches_fail_soft():
    respx.get(url__regex=r".*/recentMatches").mock(return_value=httpx.Response(500))
    assert await opendota.get_recent_matches("123") == []
