"""dota2.opendota adapter — profile mapping, normalization, rank helpers, and
the expose-data link gate. Ported from `poc-reference/tests/test_dota.py` +
the Phase-2 gate. Host calls respx-mocked."""

from __future__ import annotations

import httpx
import pytest
import respx

from moneymatch_api.adapters.dota2_opendota import Dota2OpenDotaAdapter
from moneymatch_api.services.hosts import opendota

ADAPTER = Dota2OpenDotaAdapter()
BASE = "https://api.opendota.com/api"


# --------------------------------------------------------------------------- #
# Rank helpers
# --------------------------------------------------------------------------- #


def test_rank_label_and_mmr_from_tier():
    assert opendota.rank_label(80) == "Immortal"
    assert opendota.rank_label(55) == "Legend 5"
    assert opendota.rank_label(None) is None
    assert opendota.mmr_from_rank(80) > opendota.mmr_from_rank(55)
    assert opendota.mmr_from_rank(None) == 3000


# --------------------------------------------------------------------------- #
# Profile mapping
# --------------------------------------------------------------------------- #


def test_maps_player_into_profile():
    player = {
        "profile": {"personaname": "Snake master", "avatarfull": "https://cdn/a.png"},
        "rank_tier": 80,
        "mmr_estimate": {"estimate": None},
    }
    p = ADAPTER._to_profile("70388657", player, {"win": 110, "lose": 90})
    assert p.game == "dota2.opendota"
    assert p.username == "70388657"  # numeric id is the settlement poll key
    assert p.display_name == "Snake master"
    assert p.rank_label == "Immortal"
    assert p.rating == opendota.mmr_from_rank(80)  # derived when mmr hidden
    assert p.total_games == 200
    assert p.win_rate == 0.55
    assert p.avatar_url == "https://cdn/a.png"
    assert p.formats == [] and p.primary_speed is None


def test_prefers_real_mmr_when_present():
    player = {
        "profile": {"personaname": "x"},
        "rank_tier": 55,
        "mmr_estimate": {"estimate": 4200},
    }
    p = ADAPTER._to_profile("1", player, {"win": 1, "lose": 1})
    assert p.rating == 4200


# --------------------------------------------------------------------------- #
# Match normalization (win/loss + rate telemetry)
# --------------------------------------------------------------------------- #


def test_normalize_radiant_win_with_metrics():
    g = ADAPTER._normalize(
        {
            "match_id": 1,
            "player_slot": 2,
            "radiant_win": True,
            "start_time": 1000,
            "kills": 9,
            "deaths": 3,
            "assists": 12,
            "gold_per_min": 640,
        }
    )
    assert g.won is True and g.id == "1" and g.created_at_ms == 1_000_000
    assert g.metrics["dota2_kda_ratio"] == round(21 / 3, 4)
    assert g.metrics["dota2_gpm"] == 640.0


def test_normalize_dire_loss():
    g = ADAPTER._normalize(
        {"match_id": 2, "player_slot": 130, "radiant_win": True, "start_time": 1000}
    )
    assert g.won is False


def test_normalize_skips_incomplete_rows():
    assert ADAPTER._normalize({"match_id": 3, "player_slot": 1}) is None


# --------------------------------------------------------------------------- #
# Link flow: numeric id resolution + expose-data gate
# --------------------------------------------------------------------------- #


@respx.mock
async def test_link_numeric_id_with_public_matches():
    respx.get(f"{BASE}/players/123").mock(
        return_value=httpx.Response(
            200, json={"profile": {"personaname": "hero"}, "rank_tier": 55}
        )
    )
    respx.get(f"{BASE}/players/123/wl").mock(
        return_value=httpx.Response(200, json={"win": 10, "lose": 5})
    )
    respx.get(f"{BASE}/players/123/recentMatches").mock(
        return_value=httpx.Response(
            200, json=[{"match_id": 9, "player_slot": 1, "radiant_win": True}]
        )
    )
    p = await ADAPTER.link_account("username", "123")
    assert p.username == "123" and p.display_name == "hero"


@respx.mock
async def test_link_blocks_when_match_data_not_exposed():
    respx.get(f"{BASE}/players/123").mock(
        return_value=httpx.Response(
            200, json={"profile": {"personaname": "hero"}, "rank_tier": 55}
        )
    )
    respx.get(f"{BASE}/players/123/wl").mock(
        return_value=httpx.Response(200, json={"win": 0, "lose": 0})
    )
    respx.get(f"{BASE}/players/123/recentMatches").mock(
        return_value=httpx.Response(200, json=[])  # public match data off
    )
    with pytest.raises(ValueError, match="Expose Public Match Data"):
        await ADAPTER.link_account("username", "123")


@respx.mock
async def test_fetch_profile_private_is_not_found():
    respx.get(f"{BASE}/players/999").mock(
        return_value=httpx.Response(200, json={"profile": None})
    )
    with pytest.raises(ValueError, match="not found"):
        await ADAPTER.fetch_profile("999")
