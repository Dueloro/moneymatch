"""pubg.steam adapter — profile mapping, match normalization, telemetry, fail-soft.

Host calls to the official PUBG API are respx-mocked — no live network. The
adapter is dormant (not in the registry yet), so these exercise it directly.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from moneymatch_api.adapters.pubg import PubgAdapter
from moneymatch_api.config import get_settings
from moneymatch_api.services.hosts import pubg

ADAPTER = PubgAdapter()
ACCOUNT = "account.abc123"
SHARD = "https://api.pubg.com/shards/steam"
PLAYERS = f"{SHARD}/players"


@pytest.fixture
def pubg_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "pubg_api_key", "test-key")
    pubg.clear_match_cache()
    yield
    pubg.clear_match_cache()


def _player(match_ids=()):
    return {
        "id": ACCOUNT,
        "attributes": {"name": "chocoTaco"},
        "relationships": {
            "matches": {"data": [{"type": "match", "id": m} for m in match_ids]}
        },
    }


def _lifetime():
    return {
        "data": {
            "attributes": {
                "gameModeStats": {
                    "squad-fpp": {
                        "roundsPlayed": 100,
                        "wins": 10,
                        "kills": 300,
                        "losses": 90,
                        "damageDealt": 25000.0,
                        "headshotKills": 90,
                    },
                    "solo-fpp": {
                        "roundsPlayed": 20,
                        "wins": 2,
                        "kills": 40,
                        "losses": 18,
                        "damageDealt": 4000.0,
                        "headshotKills": 12,
                    },
                }
            }
        }
    }


def _match(
    match_id, *, kills, headshots, damage, win_place, created="2026-07-24T00:00:00Z"
):
    return {
        "data": {
            "id": match_id,
            "attributes": {"gameMode": "squad-fpp", "createdAt": created},
        },
        "included": [
            {"type": "roster", "attributes": {}},
            {
                "type": "participant",
                "attributes": {
                    "stats": {
                        "playerId": ACCOUNT,
                        "kills": kills,
                        "headshotKills": headshots,
                        "damageDealt": damage,
                        "winPlace": win_place,
                    }
                },
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Profile mapping
# --------------------------------------------------------------------------- #


@respx.mock
async def test_link_account_maps_aggregated_lifetime(pubg_key):
    respx.get(PLAYERS).mock(
        return_value=httpx.Response(200, json={"data": [_player()]})
    )
    respx.get(f"{SHARD}/players/{ACCOUNT}/seasons/lifetime").mock(
        return_value=httpx.Response(200, json=_lifetime())
    )

    p = await ADAPTER.link_account("username", "chocoTaco")

    # host_account_id keys on `username`, so it must be the stable account id.
    assert p.username == ACCOUNT
    assert p.display_name == "chocoTaco"
    assert p.game == "pubg.steam"
    assert p.link_method == "username"
    assert p.total_games == 120  # 100 + 20 rounds across modes
    assert p.win_rate == round(12 / 120, 4)
    assert p.kd == round(340 / 108, 2)  # kills / losses aggregated


@respx.mock
async def test_link_account_unknown_player_raises(pubg_key):
    respx.get(PLAYERS).mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(ValueError, match="not found"):
        await ADAPTER.link_account("username", "ghost")


@respx.mock
async def test_fetch_profile_by_account_id(pubg_key):
    respx.get(f"{SHARD}/players/{ACCOUNT}").mock(
        return_value=httpx.Response(200, json={"data": _player()})
    )
    respx.get(f"{SHARD}/players/{ACCOUNT}/seasons/lifetime").mock(
        return_value=httpx.Response(200, json=_lifetime())
    )
    p = await ADAPTER.fetch_profile(ACCOUNT)
    assert p.username == ACCOUNT and p.display_name == "chocoTaco"


# --------------------------------------------------------------------------- #
# Match normalization + telemetry
# --------------------------------------------------------------------------- #


@respx.mock
async def test_poll_normalizes_matches_with_rate_metrics_and_win(pubg_key):
    respx.get(f"{SHARD}/players/{ACCOUNT}").mock(
        return_value=httpx.Response(200, json={"data": _player(["m1", "m2"])})
    )
    respx.get(f"{SHARD}/matches/m1").mock(
        return_value=httpx.Response(
            200,
            json=_match("m1", kills=9, headshots=4, damage=1219.7, win_place=1),
        )
    )
    respx.get(f"{SHARD}/matches/m2").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "m2",
                kills=0,
                headshots=0,
                damage=120.0,
                win_place=8,
                created="2026-07-23T00:00:00Z",
            ),
        )
    )

    from moneymatch_api.adapters.base import GameFilters

    games = await ADAPTER.poll_eligible_games(ACCOUNT, 0, GameFilters())

    assert [g.id for g in games] == ["m2", "m1"]  # sorted oldest-first
    win = next(g for g in games if g.id == "m1")
    assert win.won is True and win.drawn is False
    assert win.metrics["pubg_kills"] == 9.0
    assert win.metrics["pubg_damage"] == 1219.7
    assert win.metrics["pubg_headshot_pct"] == round(100 * 4 / 9, 1)
    loss = next(g for g in games if g.id == "m2")
    assert loss.won is False
    assert loss.metrics["pubg_headshot_pct"] == 0.0  # no divide-by-zero on 0 kills

    tele = ADAPTER.norm_to_telemetry(win)
    assert tele.game == "pubg.steam" and tele.metrics["pubg_kills"] == 9.0


@respx.mock
async def test_poll_filters_by_since_ms(pubg_key):
    respx.get(f"{SHARD}/players/{ACCOUNT}").mock(
        return_value=httpx.Response(200, json={"data": _player(["m1"])})
    )
    respx.get(f"{SHARD}/matches/m1").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "m1",
                kills=1,
                headshots=0,
                damage=10.0,
                win_place=5,
                created="2020-01-01T00:00:00Z",
            ),
        )
    )
    from moneymatch_api.adapters.base import GameFilters

    # since well after the match → excluded.
    games = await ADAPTER.poll_eligible_games(ACCOUNT, 9_000_000_000_000, GameFilters())
    assert games == []


# --------------------------------------------------------------------------- #
# Fail-soft without a key
# --------------------------------------------------------------------------- #


async def test_missing_key_fails_soft(monkeypatch):
    monkeypatch.setattr(get_settings(), "pubg_api_key", None)
    from moneymatch_api.adapters.base import GameFilters

    assert await pubg.get_player_by_name("x") is None
    assert await pubg.get_lifetime("account.x") is None
    assert await ADAPTER.poll_eligible_games("account.x", 0, GameFilters()) == []
    with pytest.raises(ValueError, match="not found"):
        await ADAPTER.link_account("username", "x")
