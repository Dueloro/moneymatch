"""Tests for the dota2.opendota adapter — profile mapping + H2H + rank helpers."""

from _lib import lobby, opendota_service
from _lib.adapters.base import NormGame
from _lib.adapters.dota2_opendota import Dota2OpenDotaAdapter
from _lib.schemas import SkillProfile

ADAPTER = Dota2OpenDotaAdapter()


# --------------------------------------------------------------------------- #
# Rank helpers
# --------------------------------------------------------------------------- #

def test_rank_label_and_mmr_from_tier():
    assert opendota_service.rank_label(80) == "Immortal"      # 8/0
    assert opendota_service.rank_label(55) == "Legend 5"      # 5/5
    assert opendota_service.rank_label(None) is None
    assert opendota_service.mmr_from_rank(80) > opendota_service.mmr_from_rank(55)
    assert opendota_service.mmr_from_rank(None) == 3000        # neutral default


# --------------------------------------------------------------------------- #
# Profile mapping
# --------------------------------------------------------------------------- #

def test_maps_player_into_skill_profile():
    player = {
        "profile": {"personaname": "Snake master", "avatarfull": "https://cdn/a.png"},
        "rank_tier": 80,
        "mmr_estimate": {"estimate": None},
    }
    p = ADAPTER._to_profile("70388657", player, {"win": 110, "lose": 90})
    assert p.game == "dota2.opendota"
    assert p.username == "70388657"           # numeric id is the settlement poll key
    assert p.display_name == "Snake master"
    assert p.rank_label == "Immortal"
    assert p.rating == opendota_service.mmr_from_rank(80)  # derived when mmr hidden
    assert p.total_games == 200
    assert p.win_rate == 0.55
    assert p.avatar_url == "https://cdn/a.png"
    assert p.formats == [] and p.primary_speed is None       # not a chess profile


def test_prefers_real_mmr_when_present():
    player = {"profile": {"personaname": "x"}, "rank_tier": 55, "mmr_estimate": {"estimate": 4200}}
    p = ADAPTER._to_profile("1", player, {"win": 1, "lose": 1})
    assert p.rating == 4200


# --------------------------------------------------------------------------- #
# Match normalization (win/loss from player_slot vs radiant_win)
# --------------------------------------------------------------------------- #

def test_normalize_radiant_win():
    # Radiant slot (<128) + radiant_win True → won.
    g = ADAPTER._normalize({"match_id": 1, "player_slot": 2, "radiant_win": True, "start_time": 1000})
    assert g.won is True and g.id == "1" and g.created_at_ms == 1_000_000

def test_normalize_dire_loss():
    # Dire slot (>=128) + radiant_win True → lost.
    g = ADAPTER._normalize({"match_id": 2, "player_slot": 130, "radiant_win": True, "start_time": 1000})
    assert g.won is False

def test_normalize_skips_incomplete_rows():
    assert ADAPTER._normalize({"match_id": 3, "player_slot": 1}) is None  # no radiant_win


# --------------------------------------------------------------------------- #
# Head-to-head settlement
# --------------------------------------------------------------------------- #

def _dota_contract(matched_at):
    prof = SkillProfile(username="1", display_name="x", url="u", link_method="username",
                        game="dota2.opendota", win_rate=0.5, total_games=10, rating=3000)
    c = lobby.build_contract(prof, lobby.ContractDraft(
        game="dota2.opendota", speed="dota2", format="Ranked",
        objective=lobby.Objective(kind="win_h2h"), entry=10.0))
    c.state = "ACTIVE"; c.matched_at = matched_at
    return c


def test_resolve_win_loss_and_refund():
    c = _dota_contract(5000)
    win = [NormGame(id="m", speed="dota2", rated=True, created_at_ms=6000, moves=0, won=True, drawn=False)]
    assert ADAPTER.resolve_contract(c, win, now_ms=9000).outcome == "won"

    c2 = _dota_contract(5000)
    loss = [NormGame(id="m", speed="dota2", rated=True, created_at_ms=6000, moves=0, won=False, drawn=False)]
    assert ADAPTER.resolve_contract(c2, loss, now_ms=9000).outcome == "lost"

    c3 = _dota_contract(5000)
    expired = ADAPTER.resolve_contract(c3, [], now_ms=5000 + 13 * 3_600_000)
    assert expired.state == "CANCELED" and expired.payout == c3.entry
