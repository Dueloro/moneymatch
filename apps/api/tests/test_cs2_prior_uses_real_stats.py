"""The CS2 prior must use the numbers Steam actually returned (1.4).

`GetUserStatsForGame` returns `total_kills_headshot` and `total_matches_played`
in the same response as the K/D inputs. `_derived()` ignored both and scaled a
generic default by the K/D ratio instead.

The real test account measured while writing this: K/D 0.606, headshot rate
36.6%, 8.19 kills per match. The old code seeded 42.3% and 10.9 kills, quoting
easy bars of 47% and 13 — to a player who does 36.6% and 8.19. They never clear,
lose four contests, and leave.
"""

from __future__ import annotations

import pytest

from moneymatch_api.constants import GAME_CS2_STEAM
from moneymatch_api.services import cs2_prior
from moneymatch_api.services.hosts.steam import LifetimeStats

from .factories import create_user

# No module-level asyncio mark: `asyncio_mode = "auto"` collects the async tests
# already, and applying it would warn on the two pure functions below (P2-1).

STEAM_ID = "76561198748110372"

#: The real account: 131 kills / 216 deaths / 48 headshots / 16 matches.
REAL = LifetimeStats(
    total_kills=131,
    total_deaths=216,
    total_time_played=0,
    total_matches_won=9,
    total_matches_played=16,
    total_kills_headshot=48,
)


def _stub(stats: LifetimeStats | None):
    async def _get(_steam_id):
        return stats

    return _get


async def _seed(session, monkeypatch, username: str, stats):
    monkeypatch.setattr(cs2_prior.steam, "get_cs2_lifetime_stats", _stub(stats))
    user = await create_user(session, username=username)
    values = await cs2_prior.seed(session, user.id, STEAM_ID)
    return user, values


@pytest.mark.nodb
def test_lifetime_stats_expose_the_derived_rates():
    assert REAL.kd_ratio == pytest.approx(0.6065, abs=0.001)
    assert REAL.headshot_pct == pytest.approx(36.64, abs=0.01)
    assert REAL.kills_per_match == pytest.approx(8.1875, abs=0.001)


@pytest.mark.nodb
def test_derived_rates_are_none_when_unusable():
    empty = LifetimeStats(0, 0, 0, 0, 0, 0)
    assert empty.kd_ratio is None
    assert empty.headshot_pct is None
    assert empty.kills_per_match is None


async def test_seed_uses_measured_headshot_and_kills(session, monkeypatch):
    """The headline fix: seeded means must match the player's real form."""
    _user, values = await _seed(session, monkeypatch, "real_stats", REAL)

    assert values["cs2_kd_ratio"][0] == pytest.approx(0.6065, abs=0.001)
    assert values["cs2_headshot_pct"][0] == pytest.approx(36.64, abs=0.05)
    assert values["cs2_kills"][0] == pytest.approx(8.1875, abs=0.01)


async def test_seed_no_longer_inflates_this_account(session, monkeypatch):
    """Named explicitly: the old numbers must not come back."""
    _user, values = await _seed(session, monkeypatch, "no_inflation", REAL)
    assert values["cs2_headshot_pct"][0] < 40.0, "was 42.34 under the old heuristic"
    assert values["cs2_kills"][0] < 9.5, "was 10.92 under the old heuristic"


async def test_private_profile_still_falls_back_to_defaults(session, monkeypatch):
    """The documented normal path: game details private → 400 → None."""
    _user, values = await _seed(session, monkeypatch, "private_profile", None)
    assert values["cs2_kd_ratio"][0] == pytest.approx(1.00)
    assert values["cs2_headshot_pct"][0] == pytest.approx(45.0)
    assert values["cs2_kills"][0] == pytest.approx(18.0)


async def test_partial_stats_improve_only_what_is_measured(session, monkeypatch):
    """A profile with kills and deaths but no headshot counter."""
    partial = LifetimeStats(
        total_kills=1000,
        total_deaths=1000,
        total_time_played=0,
        total_matches_won=30,
        total_matches_played=100,
        total_kills_headshot=0,  # absent
    )
    _user, values = await _seed(session, monkeypatch, "partial_stats", partial)
    # Measured: K/D 1.0 and 10 kills per match.
    assert values["cs2_kd_ratio"][0] == pytest.approx(1.0, abs=0.001)
    assert values["cs2_kills"][0] == pytest.approx(10.0, abs=0.01)
    # Not measured: falls back to the derived heuristic, not to nonsense.
    assert values["cs2_headshot_pct"][0] == pytest.approx(45.0, abs=0.01)


@pytest.mark.parametrize(
    ("hs_kills", "matches", "why"),
    [
        (990, 100, "implausible headshot rate (99%)"),
        (5, 100, "implausible headshot rate (0.5%)"),
    ],
)
async def test_implausible_measurements_are_ignored(
    session, monkeypatch, hs_kills, matches, why
):
    """A bot-farmed or broken counter must not become somebody's bar."""
    stats = LifetimeStats(
        total_kills=1000,
        total_deaths=1000,
        total_time_played=0,
        total_matches_won=30,
        total_matches_played=matches,
        total_kills_headshot=hs_kills,
    )
    _user, values = await _seed(session, monkeypatch, f"implausible_{hs_kills}", stats)
    assert values["cs2_headshot_pct"][0] == pytest.approx(45.0, abs=0.01), why


async def test_seeded_bars_track_real_form(session, monkeypatch):
    """End to end: the bars a real account would now be quoted."""
    from moneymatch_api.services import pool_engine

    from .factories import create_linked_account, cs2_profile

    user, _values = await _seed(session, monkeypatch, "real_bars", REAL)
    await create_linked_account(
        session,
        user,
        GAME_CS2_STEAM,
        host_account_id=STEAM_ID,
        profile=cs2_profile("real"),
    )

    kills = await pool_engine.preview_bars(session, user, GAME_CS2_STEAM, "cs2_kills")
    easy = next(c["bar"] for c in kills["cards"] if c["difficulty"] == "easy")
    # Old heuristic quoted 13 kills to an 8.19-kill player. Must now be lower.
    assert easy < 13, f"easy kills bar {easy} is still above the old inflated 13"
