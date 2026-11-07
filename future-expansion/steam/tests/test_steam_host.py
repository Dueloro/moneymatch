"""The Steam Web API client: parsing, and what happens when Steam says no.

Live-checked on 2026-08-11 against a real key: `GetPlayerSummaries` and
`GetPlayerBans` both answer for any public account, and `GetUserStatsForGame`
returned nothing for both accounts tried. That is not a bug and not rare: the
endpoint needs the profile's *Game details* to be public, and most are not. So
the fallback is the common path, not the edge case, and it is tested as such.
"""

from __future__ import annotations

import pytest

from moneymatch_api.services.hosts import steam

pytestmark = pytest.mark.nodb


@pytest.fixture
def steam_says(monkeypatch):
    """Stub the one function that talks to Steam."""

    def _install(payload):
        async def fake_get(path, params):
            return payload

        monkeypatch.setattr(steam, "_get", fake_get)

    return _install


# --------------------------------------------------------------------------- #
# Bans.
# --------------------------------------------------------------------------- #


def _ban_payload(**over):
    row = {
        "SteamId": "7656119",
        "CommunityBanned": False,
        "VACBanned": False,
        "NumberOfVACBans": 0,
        "DaysSinceLastBan": 0,
        "NumberOfGameBans": 0,
        "EconomyBan": "none",
    }
    row.update(over)
    return {"players": [row]}


async def test_a_clean_account_reads_as_clean(steam_says):
    steam_says(_ban_payload())
    status = await steam.get_player_bans("7656119")
    assert status is not None and status.is_clean is True


@pytest.mark.parametrize(
    "over",
    [
        {"VACBanned": True, "NumberOfVACBans": 1},
        {"NumberOfGameBans": 2},
        {"CommunityBanned": True},
    ],
)
async def test_any_ban_makes_the_account_unclean(steam_says, over):
    """Checked before money moves, so 'clean' must mean all three."""
    steam_says(_ban_payload(**over))
    status = await steam.get_player_bans("7656119")
    assert status is not None and status.is_clean is False


async def test_an_unavailable_ban_lookup_is_not_a_clean_account(steam_says):
    """`None` means unknown. It must never be mistaken for 'no bans'."""
    steam_says(None)
    assert await steam.get_player_bans("7656119") is None


# --------------------------------------------------------------------------- #
# Lifetime stats, the skill prior.
# --------------------------------------------------------------------------- #


def _stats_payload(kills: int, deaths: int):
    return {
        "playerstats": {
            "stats": [
                {"name": "total_kills", "value": kills},
                {"name": "total_deaths", "value": deaths},
                {"name": "total_time_played", "value": 360000},
                {"name": "total_matches_won", "value": 40},
                {"name": "total_matches_played", "value": 90},
            ]
        }
    }


async def test_lifetime_kd_is_kills_over_deaths(steam_says):
    steam_says(_stats_payload(2400, 2000))
    stats = await steam.get_cs2_lifetime_stats("7656119")
    assert stats is not None
    assert stats.kd_ratio == pytest.approx(1.2)


async def test_a_private_profile_yields_no_stats(steam_says):
    """The common case. Steam answers 403 and the caller falls back."""
    steam_says(None)
    assert await steam.get_cs2_lifetime_stats("7656119") is None


async def test_an_empty_stats_block_yields_no_stats(steam_says):
    steam_says({"playerstats": {}})
    assert await steam.get_cs2_lifetime_stats("7656119") is None


async def test_zero_deaths_does_not_divide_by_zero(steam_says):
    steam_says(_stats_payload(10, 0))
    stats = await steam.get_cs2_lifetime_stats("7656119")
    assert stats is not None and stats.kd_ratio is None


# --------------------------------------------------------------------------- #
# Identity.
# --------------------------------------------------------------------------- #


async def test_a_vanity_url_resolves_to_a_steamid(steam_says):
    steam_says({"response": {"success": 1, "steamid": "76561197960287930"}})
    assert await steam.resolve_vanity_url("gabelogannewell") == "76561197960287930"


async def test_an_unresolvable_vanity_url_is_none(steam_says):
    """Steam reports failure with success=42, which is not an error code we
    should surface as a crash."""
    steam_says({"response": {"success": 42, "message": "No match"}})
    assert await steam.resolve_vanity_url("nobody-here") is None


async def test_the_client_reports_whether_it_is_configured(monkeypatch):
    from moneymatch_api.config import get_settings

    monkeypatch.setenv("STEAM_API_KEY", "")
    get_settings.cache_clear()
    assert steam.is_configured() is False
    monkeypatch.setenv("STEAM_API_KEY", "0" * 32)
    get_settings.cache_clear()
    assert steam.is_configured() is True
    get_settings.cache_clear()
