"""cs2.faceit adapter — profile mapping, normalization, telemetry, CS:GO reject.

Ported from `poc-reference/tests/test_faceit.py` (parsing/normalization portions).
Settlement grading moves to Phase 3 with the Match model. Host calls are
respx-mocked — no live network.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.adapters.cs2_faceit import CS2FaceitAdapter, _extract_player_metrics
from moneymatch_api.config import get_settings
from moneymatch_api.services.hosts import faceit

ADAPTER = CS2FaceitAdapter()
PID = "me-player-id"
PLAYERS_URL = "https://open.faceit.com/data/v4/players"


@pytest.fixture
def faceit_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "faceit_api_key", "test-key")
    faceit.clear_match_cache()
    yield
    faceit.clear_match_cache()


def _history_item(match_id, winner, my_faction, started=1000, status="finished"):
    other = "faction2" if my_faction == "faction1" else "faction1"
    return {
        "match_id": match_id,
        "status": status,
        "started_at": started,
        "results": {"winner": winner},
        "teams": {
            my_faction: {"players": [{"player_id": PID}, {"player_id": "teammate"}]},
            other: {"players": [{"player_id": "opp1"}, {"player_id": "opp2"}]},
        },
    }


# --------------------------------------------------------------------------- #
# Profile mapping
# --------------------------------------------------------------------------- #


def test_maps_faceit_player_into_profile():
    player = {
        "player_id": "abc",
        "nickname": "ZywOo",
        "avatar": "https://cdn/x.png",
        "faceit_url": "https://www.faceit.com/{lang}/players/ZywOo",
        "games": {"cs2": {"skill_level": 10, "faceit_elo": 4017, "region": "EU"}},
    }
    cs2 = player["games"]["cs2"]
    stats = {"Matches": "4734", "Win Rate %": "70", "Average K/D Ratio": "1.7"}

    p = ADAPTER._to_profile(player, cs2, stats)
    assert p.game == "cs2.faceit"
    assert p.username == "ZywOo" and p.display_name == "ZywOo"
    assert p.rating == 4017
    assert p.rank_label == "Level 10"
    assert p.kd == 1.7
    assert p.total_games == 4734
    assert p.win_rate == 0.7
    assert p.avatar_url == "https://cdn/x.png"
    assert "{lang}" not in p.url and p.url.endswith("/players/ZywOo")
    assert p.formats == [] and p.primary_speed is None


def test_handles_missing_stats_gracefully():
    player = {
        "player_id": "abc",
        "nickname": "newbie",
        "games": {"cs2": {"skill_level": 1}},
    }
    p = ADAPTER._to_profile(player, player["games"]["cs2"], {})
    assert p.rating is None
    assert p.rank_label == "Level 1"
    assert p.kd is None
    assert p.total_games == 0
    assert p.win_rate == 0.5


# --------------------------------------------------------------------------- #
# Match-history normalization
# --------------------------------------------------------------------------- #


def test_normalize_win_and_loss():
    won = ADAPTER._normalize(
        _history_item("m1", winner="faction1", my_faction="faction1"), PID
    )
    assert won is not None and won.won is True and won.id == "m1"
    assert won.created_at_ms == 1000 * 1000  # epoch seconds → ms

    lost = ADAPTER._normalize(
        _history_item("m2", winner="faction2", my_faction="faction1"), PID
    )
    assert lost.won is False


def test_normalize_skips_unfinished_and_absent_player():
    assert (
        ADAPTER._normalize(
            _history_item("m", "faction1", "faction1", status="ongoing"), PID
        )
        is None
    )
    item = _history_item("m", "faction1", "faction1")
    assert ADAPTER._normalize(item, "someone-else") is None


# --------------------------------------------------------------------------- #
# Per-match metrics + telemetry
# --------------------------------------------------------------------------- #


def _match_stats(pid, **player_stats):
    return {
        "rounds": [
            {
                "teams": [
                    {
                        "players": [
                            {"player_id": pid, "player_stats": player_stats},
                            {"player_id": "other", "player_stats": {"Kills": "5"}},
                        ]
                    }
                ]
            }
        ]
    }


def test_extract_player_metrics_confirmed_keys():
    stats = _match_stats(
        PID,
        **{
            "Kills": "29",
            "Deaths": "24",
            "K/D Ratio": "1.21",
            "Headshots %": "66",
            "ADR": "97.7",
            "MVPs": "6",
        },
    )
    m = _extract_player_metrics(stats, PID)
    assert m == {
        "cs2_kills": 29.0,
        "cs2_deaths": 24.0,
        "cs2_kd_ratio": 1.21,
        "cs2_headshot_pct": 66.0,
        "cs2_adr": 97.7,
        "cs2_mvps": 6.0,
    }


def test_extract_player_metrics_omits_absent_fields():
    m = _extract_player_metrics(_match_stats(PID, **{"Kills": "20"}), PID)
    assert m == {"cs2_kills": 20.0}
    assert _extract_player_metrics(_match_stats("nobody", Kills="20"), PID) == {}


def test_norm_to_telemetry_carries_metrics():
    norm = NormGame(
        id="m1",
        speed="cs2",
        rated=True,
        created_at_ms=0,
        moves=0,
        won=True,
        drawn=False,
        metrics={"cs2_kills": 22.0, "cs2_adr": 90.0},
    )
    sample = CS2FaceitAdapter.norm_to_telemetry(norm)
    assert sample.game == "cs2.faceit"
    assert sample.metrics == {"cs2_kills": 22.0, "cs2_adr": 90.0}


# --------------------------------------------------------------------------- #
# fetch_profile against a mocked host (link path)
# --------------------------------------------------------------------------- #


@respx.mock
async def test_fetch_profile_end_to_end(faceit_key):
    respx.get(PLAYERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "player_id": "abc",
                "nickname": "s1mple",
                "faceit_url": "https://www.faceit.com/{lang}/players/s1mple",
                "games": {"cs2": {"skill_level": 10, "faceit_elo": 3900}},
            },
        )
    )
    respx.get("https://open.faceit.com/data/v4/players/abc/stats/cs2").mock(
        return_value=httpx.Response(
            200, json={"lifetime": {"Matches": "100", "Win Rate %": "60"}}
        )
    )
    p = await ADAPTER.link_account("username", "s1mple")
    assert p.username == "s1mple" and p.rating == 3900 and p.link_method == "username"


@respx.mock
async def test_fetch_profile_rejects_csgo_only(faceit_key):
    respx.get(PLAYERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "player_id": "x",
                "nickname": "legacy",
                "games": {"csgo": {"faceit_elo": 1500}},
            },
        )
    )
    with pytest.raises(ValueError, match="no CS2 activity"):
        await ADAPTER.fetch_profile("legacy")
