"""What number a CS2 wager asks you for.

A bar has to be hard enough to be worth winning and close enough to be worth
trying. The failure that prompted this: a player who had just gone 8-19 was
offered "clear 1.25 K/D", because the bar came from a fixed default instead of
from anything about them.

The lobby is the interesting source. Every resolved match carries nine other
scoreboards, and Valve put those people there because it thinks they are your
level, so it is a free read on "players around my rank". It has to be weighted
carefully in both directions: enough to be useful when we know nothing about
you, little enough that it stops mattering once we do.
"""

from __future__ import annotations

import pytest

from moneymatch_api.services.cs2_baseline import POPULATION, compute

pytestmark = pytest.mark.nodb

#: The nine other K/D lines from a real match, including one player on a
#: completely different level (39 kills, 12 deaths).
LOBBY = [39 / 12, 21 / 18, 13 / 14, 8 / 16, 6 / 19, 27 / 15, 18 / 19, 13 / 18, 11 / 18]

#: The submitter's own line from that match.
POOR_GAME = 8 / 19  # 0.42


def kd(own, cohort=LOBBY, lifetime=None):
    return compute("cs2_kd_ratio", own, cohort, lifetime)


# --------------------------------------------------------------------------- #
# The reported problem.
# --------------------------------------------------------------------------- #


def test_a_bad_game_pulls_the_bar_down_toward_you():
    """The bar must move after one real result, or it is not your bar."""
    cold = kd([])
    after = kd([POOR_GAME])
    assert after.mu < cold.mu
    # And it must land nearer the player than the population guess.
    assert after.mu < POPULATION["cs2_kd_ratio"][0]


def test_your_own_record_wins_once_there_is_some_of_it():
    """Five poor games should read as a poor player, not an average one."""
    consistent = kd([0.42, 0.50, 0.60, 0.45, 0.55])
    assert consistent.mu < 0.75
    assert consistent.source == "own"


def test_a_strong_player_is_quoted_a_higher_bar():
    assert kd([2.1, 1.9, 2.4, 2.0, 2.2]).mu > kd([0.4, 0.5, 0.45, 0.6, 0.5]).mu


# --------------------------------------------------------------------------- #
# The lobby, and its one dangerous property.
# --------------------------------------------------------------------------- #


def test_one_smurf_does_not_set_everyone_elses_bar():
    """A median, not a mean: one 3.25 K/D player is real but not the bracket."""
    ordinary = [0.8, 0.9, 1.0, 1.1, 1.2]
    with_smurf = [*ordinary, 6.0]
    assert kd([], with_smurf).mu == pytest.approx(kd([], ordinary).mu, abs=0.1)


def test_the_lobby_is_used_when_nothing_is_known_about_you():
    low = kd([], [0.4, 0.5, 0.45, 0.55, 0.5])
    high = kd([], [2.0, 2.2, 1.9, 2.1, 2.0])
    assert low.mu < high.mu


def test_the_lobby_stops_mattering_once_you_have_a_record():
    """Otherwise a good player in weak lobbies is quoted a soft bar forever."""
    own = [2.0, 2.1, 1.9, 2.2, 2.0, 2.1]
    weak_lobby = kd(own, [0.4, 0.5, 0.45])
    strong_lobby = kd(own, [2.5, 2.6, 2.4])
    assert abs(weak_lobby.mu - strong_lobby.mu) < 0.25


def test_with_nothing_at_all_it_falls_back_to_the_population():
    cold = compute("cs2_kd_ratio", [], [])
    assert cold.mu == pytest.approx(POPULATION["cs2_kd_ratio"][0])
    assert cold.source == "population"


# --------------------------------------------------------------------------- #
# Spread. A bar is centre plus k*spread, so this decides reachability.
# --------------------------------------------------------------------------- #


def test_a_lucky_streak_is_not_treated_as_consistency():
    """Three near-identical games are a small sample, not a metronome."""
    baseline = kd([1.0, 1.01, 0.99])
    assert baseline.sigma > 0.05


def test_one_wild_lobby_cannot_produce_an_unreachable_bar():
    baseline = kd([], [0.1, 0.2, 6.0, 7.0])
    assert baseline.sigma <= abs(baseline.mu) * 0.46


@pytest.mark.parametrize("metric", list(POPULATION))
def test_every_metric_has_a_usable_spread(metric):
    baseline = compute(metric, [], [])
    assert baseline.sigma > 0
    assert baseline.mu > 0


# --------------------------------------------------------------------------- #
# Lifetime stats, the weakest source.
# --------------------------------------------------------------------------- #


def test_lifetime_kd_only_nudges_a_player_with_no_matches():
    """It is cumulative across casual, deathmatch and bot games, so it never
    substitutes for a real result."""
    cold_default = kd([], LOBBY, None)
    cold_strong = kd([], LOBBY, 2.4)
    assert cold_strong.mu > cold_default.mu

    # With real matches present it must not move the answer.
    own = [0.42, 0.5, 0.45]
    assert kd(own, LOBBY, 2.4).mu == pytest.approx(kd(own, LOBBY, None).mu)


def test_the_source_is_reported_so_a_bar_can_be_explained():
    assert compute("cs2_kd_ratio", [], []).source == "population"
    assert "cohort" in kd([POOR_GAME]).source
    assert kd([0.4] * 6).source == "own"
