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


# --------------------------------------------------------------------------- #
# Outliers. One game should not decide what you are asked for next month.
# --------------------------------------------------------------------------- #


def test_one_incredible_game_does_not_set_the_bar():
    """A player who had the night of their life still gets their real bar."""
    ordinary = [0.5, 0.55, 0.6, 0.45, 0.5, 0.55]
    with_spike = [*ordinary, 4.0]
    assert kd(with_spike).mu == pytest.approx(kd(ordinary).mu, abs=0.12)


def test_one_disaster_game_does_not_hand_out_a_free_bar():
    ordinary = [1.4, 1.5, 1.45, 1.55, 1.5, 1.4]
    with_dud = [*ordinary, 0.05]
    assert kd(with_dud).mu > kd(ordinary).mu - 0.12


def test_trimming_waits_until_there_is_something_to_spare():
    """With three matches, dropping the extremes discards most of the evidence."""
    assert kd([0.4, 0.5, 2.0]).mu > kd([0.4, 0.5, 0.6]).mu


# --------------------------------------------------------------------------- #
# The ratchet: tanking a bar has to cost more than it pays.
# --------------------------------------------------------------------------- #


def test_an_established_bar_cannot_be_tanked_in_one_match():
    from moneymatch_api.services.cs2_baseline import apply_ratchet

    assert apply_ratchet(0.30, 1.50, 8) == pytest.approx(1.38)


def test_a_bar_still_rises_freely():
    """Getting better is not an exploit, and a stale bar is a free win."""
    from moneymatch_api.services.cs2_baseline import apply_ratchet

    assert apply_ratchet(2.4, 1.0, 20) == 2.4


def test_a_new_player_converges_to_their_real_level_immediately():
    """The original bug was a player who went 8-19 being asked for 1.25."""
    from moneymatch_api.services.cs2_baseline import apply_ratchet

    assert apply_ratchet(0.42, 1.00, 2) == 0.42


def test_an_honest_decline_still_gets_there():
    from moneymatch_api.services.cs2_baseline import apply_ratchet

    mu = 1.50
    for _ in range(12):
        mu = apply_ratchet(0.60, mu, 10)
    assert mu < 0.70


# --------------------------------------------------------------------------- #
# Anomalies: flagged for review, never auto-blocked.
# --------------------------------------------------------------------------- #


def test_a_sudden_jump_beyond_your_level_is_flagged():
    """What an account looks like when somebody else starts playing on it."""
    baseline = kd([0.5, 0.55, 0.6, 0.5, 0.55, 3.0, 3.2, 3.1])
    assert "improbable_improvement" in baseline.anomalies


def test_a_sustained_drop_is_flagged_as_possible_tanking():
    baseline = kd([2.0, 2.1, 1.9, 2.0, 2.1, 0.1, 0.15, 0.1])
    assert "sustained_underperformance" in baseline.anomalies


def test_ordinary_variance_is_not_flagged():
    """A player having a normal run must not land in a review queue."""
    assert kd([1.0, 1.3, 0.8, 1.1, 0.9, 1.2, 1.0, 0.95]).anomalies == ()


def test_a_short_history_is_never_flagged():
    """Three matches cannot establish what is abnormal for anyone."""
    assert kd([0.4, 3.5, 0.5]).anomalies == ()
