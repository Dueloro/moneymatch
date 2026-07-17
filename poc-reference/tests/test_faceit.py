"""Tests for the cs2.faceit adapter — profile mapping + H2H settlement (pure)."""

import asyncio

import pytest

from _lib import faceit_service, lobby
from _lib.adapters.base import NormGame
from _lib.adapters.cs2_faceit import CS2FaceitAdapter, _extract_player_metrics
from _lib.schemas import SkillProfile

ADAPTER = CS2FaceitAdapter()

PID = "me-player-id"


def _history_item(match_id, winner, my_faction, started=1000, status="finished"):
    """A FaceIt history item placing PID in ``my_faction``."""
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


def _cs2_profile():
    return SkillProfile(
        username="me", display_name="me", url="x", link_method="username",
        game="cs2.faceit", win_rate=0.5, total_games=100, rating=2000,
    )


def _cs2_contract(matched_at):
    c = lobby.build_contract(
        _cs2_profile(),
        lobby.ContractDraft(game="cs2.faceit", speed="cs2", format="Competitive",
                            objective=lobby.Objective(kind="win_h2h"), entry=10.0),
    )
    c.state = "ACTIVE"
    c.matched_at = matched_at
    return c


def test_maps_faceit_player_into_skill_profile():
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
    # Chess-specific fields stay empty for a FaceIt profile.
    assert p.formats == [] and p.primary_speed is None


def test_handles_missing_stats_gracefully():
    player = {
        "player_id": "abc",
        "nickname": "newbie",
        "games": {"cs2": {"skill_level": 1}},  # no elo, no avatar
    }
    p = ADAPTER._to_profile(player, player["games"]["cs2"], {})
    assert p.rating is None
    assert p.rank_label == "Level 1"
    assert p.kd is None
    assert p.total_games == 0
    assert p.win_rate == 0.5  # neutral default when win rate unknown


# --------------------------------------------------------------------------- #
# Match-history normalization
# --------------------------------------------------------------------------- #

def test_normalize_win_and_loss():
    won = ADAPTER._normalize(_history_item("m1", winner="faction1", my_faction="faction1"), PID)
    assert won is not None and won.won is True and won.id == "m1"
    assert won.created_at_ms == 1000 * 1000  # epoch seconds → ms

    lost = ADAPTER._normalize(_history_item("m2", winner="faction2", my_faction="faction1"), PID)
    assert lost.won is False


def test_normalize_skips_unfinished_and_absent_player():
    assert ADAPTER._normalize(_history_item("m", "faction1", "faction1", status="ongoing"), PID) is None
    item = _history_item("m", "faction1", "faction1")
    assert ADAPTER._normalize(item, "someone-else") is None  # PID not in either team


# --------------------------------------------------------------------------- #
# Head-to-head settlement
# --------------------------------------------------------------------------- #

def test_resolve_settles_a_win():
    c = _cs2_contract(matched_at=5000)
    games = [NormGame(id="m1", speed="cs2", rated=True, created_at_ms=6000, moves=0, won=True, drawn=False)]
    r = ADAPTER.resolve_contract(c, games, now_ms=10_000)
    assert r.state == "SETTLED" and r.outcome == "won" and r.winner == "you"
    assert r.payout == c.prize
    assert r.qualifying_game_ids == ["m1"]


def test_resolve_settles_a_loss():
    c = _cs2_contract(matched_at=5000)
    games = [NormGame(id="m1", speed="cs2", rated=True, created_at_ms=6000, moves=0, won=False, drawn=False)]
    r = ADAPTER.resolve_contract(c, games, now_ms=10_000)
    assert r.state == "SETTLED" and r.outcome == "lost" and r.payout == 0.0


def test_resolve_ignores_matches_before_the_contract():
    c = _cs2_contract(matched_at=5000)
    # Match finished before the contract was made → not eligible; window still open.
    games = [NormGame(id="old", speed="cs2", rated=True, created_at_ms=4000, moves=0, won=True, drawn=False)]
    r = ADAPTER.resolve_contract(c, games, now_ms=6000)
    assert r.state == "ACTIVE"


def test_resolve_refunds_on_expired_window():
    c = _cs2_contract(matched_at=5000)  # window_hours=12
    now = 5000 + 13 * 3_600_000
    r = ADAPTER.resolve_contract(c, [], now_ms=now)
    assert r.state == "CANCELED" and r.outcome == "refunded" and r.payout == c.entry


# --------------------------------------------------------------------------- #
# Per-match metrics (real telemetry for solo grading + the FaceIt Lab)
# --------------------------------------------------------------------------- #

def _match_stats(pid, **player_stats):
    """A /matches/{id}/stats payload with one player's stats block."""
    return {"rounds": [{"teams": [
        {"players": [
            {"player_id": pid, "player_stats": player_stats},
            {"player_id": "other", "player_stats": {"Kills": "5"}},
        ]},
    ]}]}


def test_extract_player_metrics_confirmed_keys():
    """ADR is the contribution metric — FaceIt has no per-player 'Score' field."""
    stats = _match_stats(
        PID, **{"Kills": "29", "Deaths": "24", "K/D Ratio": "1.21",
                "Headshots %": "66", "ADR": "97.7", "MVPs": "6"},
    )
    m = _extract_player_metrics(stats, PID)
    assert m == {
        "cs2_kills": 29.0, "cs2_deaths": 24.0, "cs2_kd_ratio": 1.21,
        "cs2_headshot_pct": 66.0, "cs2_adr": 97.7, "cs2_mvps": 6.0,
    }


def test_extract_player_metrics_omits_absent_fields():
    """A missing field is omitted, never guessed."""
    m = _extract_player_metrics(_match_stats(PID, **{"Kills": "20"}), PID)
    assert m == {"cs2_kills": 20.0}
    assert _extract_player_metrics(_match_stats("nobody", Kills="20"), PID) == {}


def test_norm_to_telemetry_carries_metrics():
    norm = NormGame(id="m1", speed="cs2", rated=True, created_at_ms=0, moves=0,
                    won=True, drawn=False, metrics={"cs2_kills": 22.0, "cs2_adr": 90.0})
    sample = CS2FaceitAdapter.norm_to_telemetry(norm)
    assert sample.game == "cs2.faceit"
    assert sample.metrics == {"cs2_kills": 22.0, "cs2_adr": 90.0}


# --------------------------------------------------------------------------- #
# CS:GO-only accounts are rejected (legacy csgo is out of scope)
# --------------------------------------------------------------------------- #

def test_fetch_profile_rejects_csgo_only(monkeypatch):
    async def fake_get_player(nickname, game="cs2"):
        return {"player_id": "x", "nickname": nickname, "games": {"csgo": {"faceit_elo": 1500}}}

    monkeypatch.setattr(faceit_service, "get_player", fake_get_player)
    with pytest.raises(ValueError, match="no CS2 activity"):
        asyncio.run(ADAPTER.fetch_profile("legacy-csgo-player"))
