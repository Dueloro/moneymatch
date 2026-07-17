"""Adapter registry: resolution + feature-flag filtering."""

from __future__ import annotations

import pytest

from moneymatch_api.adapters import registry
from moneymatch_api.constants import REGISTERED_GAMES, game_flag_key


def test_all_ids_matches_registered_games():
    assert set(registry.all_ids()) == set(REGISTERED_GAMES)


def test_get_unknown_game_raises():
    with pytest.raises(ValueError, match="No adapter registered"):
        registry.get("rocketleague.psyonix")


def test_enabled_ids_filters_by_flag():
    flags = {game_flag_key(g): True for g in REGISTERED_GAMES}
    flags[game_flag_key("cs2.faceit")] = False
    enabled = registry.enabled_ids(flags)
    assert "cs2.faceit" not in enabled
    assert "chess.lichess" in enabled
    assert registry.is_enabled("cs2.faceit", flags) is False


def test_absent_flag_defaults_enabled():
    assert registry.is_enabled("chess.lichess", {}) is True
