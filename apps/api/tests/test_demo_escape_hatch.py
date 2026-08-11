"""The demo escape hatch: injected results, and settling on command.

A live demo of a wager product has to show a contest settling, and settlement
reads real match history from a game host. For CS2 that is a 40-minute FaceIt
match with ten people in it. Neither that nor a tournament's 48-hour window is
schedulable around an audience, so an admin can inject a finished match and
force a contest to settle.

The property that makes this honest, and the reason these tests exist:

**An injected result enters at the same seam a real one does.** Everything that
reads match history goes through `registry.get(game).poll_eligible_games()`, so
that is the only place injection happens. There is no `if simulated` branch in
grading, the pool engine or the payout path. If there were, a green demo would
stop being evidence that the real path works.

**It is inert unless switched on.** Two gates: `DEMO_SIMULATE_ENABLED`, and an
admin-only endpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import GameFilters
from moneymatch_api.adapters.cs2_faceit import CS2FaceitAdapter
from moneymatch_api.adapters.simulated import SimulatedGamesAdapter
from moneymatch_api.config import get_settings
from moneymatch_api.services import demo_simulation

from .factories import create_linked_account, create_user, cs2_profile

pytestmark = pytest.mark.asyncio

GAME = "cs2.faceit"


@pytest.fixture
def simulation_on(monkeypatch):
    """Turn the flag on for one test, and clear the settings cache."""
    monkeypatch.setenv("DEMO_SIMULATE_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def simulation_off(monkeypatch):
    monkeypatch.delenv("DEMO_SIMULATE_ENABLED", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# The flag is the outer gate.
# --------------------------------------------------------------------------- #


async def test_the_adapter_is_untouched_when_the_flag_is_off(simulation_off):
    assert demo_simulation.is_enabled() is False
    assert type(registry.get(GAME)) is CS2FaceitAdapter


async def test_the_adapter_is_wrapped_when_the_flag_is_on(simulation_on):
    assert demo_simulation.is_enabled() is True
    assert isinstance(registry.get(GAME), SimulatedGamesAdapter)


async def test_injected_rows_are_unreadable_when_the_flag_is_off(
    session, simulation_off
):
    """A row left over from a demo must not leak into a later real contest."""
    user = await create_user(session)
    await create_linked_account(
        session, user, GAME, host_account_id="nick", profile=cs2_profile("nick")
    )
    await demo_simulation.record(
        session,
        user_id=user.id,
        game=GAME,
        host_account_id="nick",
        metrics={"cs2_kd_ratio": 9.9},
        won=True,
        created_by="test",
    )
    await session.commit()

    assert await demo_simulation.games_for(GAME, "nick", 0, "cs2") == []


# --------------------------------------------------------------------------- #
# The wrapper behaves like a host feed.
# --------------------------------------------------------------------------- #


async def test_an_injected_match_appears_in_match_history(session, simulation_on):
    user = await create_user(session)
    await create_linked_account(
        session, user, GAME, host_account_id="nick2", profile=cs2_profile("nick2")
    )
    await demo_simulation.record(
        session,
        user_id=user.id,
        game=GAME,
        host_account_id="nick2",
        metrics={"cs2_kd_ratio": 1.62, "cs2_adr": 91.3},
        won=True,
        rounds=22,
        played_at=datetime.now(UTC),
        created_by="test",
    )
    await session.commit()

    games = await demo_simulation.games_for(GAME, "nick2", 0, "cs2")
    assert len(games) == 1
    game = games[0]
    assert game.won is True
    assert game.metrics["cs2_kd_ratio"] == pytest.approx(1.62)
    # Shaped so grading needs no translation: it is a NormGame like any other.
    assert game.id.startswith("sim-")


async def test_history_is_scoped_to_one_host_account(session, simulation_on):
    """Keyed by host account, exactly as a real feed is."""
    user = await create_user(session)
    await create_linked_account(
        session, user, GAME, host_account_id="mine", profile=cs2_profile("mine")
    )
    await demo_simulation.record(
        session,
        user_id=user.id,
        game=GAME,
        host_account_id="mine",
        metrics={"cs2_kd_ratio": 2.0},
        won=True,
        created_by="test",
    )
    await session.commit()

    assert len(await demo_simulation.games_for(GAME, "mine", 0, "cs2")) == 1
    assert await demo_simulation.games_for(GAME, "someone_else", 0, "cs2") == []


async def test_history_respects_the_window(session, simulation_on):
    """A match from before the contest opened must not settle it."""
    user = await create_user(session)
    await create_linked_account(
        session, user, GAME, host_account_id="windowed", profile=cs2_profile("windowed")
    )
    old = datetime.fromtimestamp(1_700_000_000, UTC)
    await demo_simulation.record(
        session,
        user_id=user.id,
        game=GAME,
        host_account_id="windowed",
        metrics={"cs2_kd_ratio": 2.0},
        won=True,
        played_at=old,
        created_by="test",
    )
    await session.commit()

    since = int(datetime.now(UTC).timestamp() * 1000)
    assert await demo_simulation.games_for(GAME, "windowed", since, "cs2") == []
    assert len(await demo_simulation.games_for(GAME, "windowed", 0, "cs2")) == 1


async def test_injected_matches_are_held_to_the_same_filters(session, simulation_on):
    """An injected result must not demonstrate a settlement a real match of the
    same shape could not have produced."""
    user = await create_user(session)
    await create_linked_account(
        session, user, GAME, host_account_id="filtered", profile=cs2_profile("filtered")
    )
    await demo_simulation.record(
        session,
        user_id=user.id,
        game=GAME,
        host_account_id="filtered",
        metrics={"cs2_kd_ratio": 2.0},
        won=True,
        created_by="test",
    )
    await session.commit()

    adapter = registry.get(GAME)
    kept = await adapter.poll_eligible_games(
        "filtered", 0, GameFilters(rated_only=False)
    )
    assert len(kept) == 1
    # A speed filter the injected match does not satisfy drops it, as it would
    # drop a real match.
    dropped = await adapter.poll_eligible_games(
        "filtered", 0, GameFilters(rated_only=False, speeds={"blitz"})
    )
    assert dropped == []


# --------------------------------------------------------------------------- #
# The endpoints.
# --------------------------------------------------------------------------- #


async def test_simulate_result_is_admin_only(session, client, simulation_on):
    from .conftest import auth_headers

    user = await create_user(session, username="plainuser")
    user.auth_id = "auth_plain_sim"
    await create_linked_account(
        session,
        user,
        GAME,
        host_account_id="plainnick",
        profile=cs2_profile("plainnick"),
    )
    await session.commit()

    r = await client.post(
        "/api/v1/demo/simulate_result",
        json={"game": GAME, "metrics": {"cs2_kd_ratio": 1.5}},
        headers=auth_headers("auth_plain_sim"),
    )
    assert r.status_code == 403, r.text


async def test_simulate_result_is_hidden_when_the_flag_is_off(
    session, client, simulation_off
):
    from .conftest import auth_headers

    admin = await create_user(session, username="adminoff")
    admin.auth_id = "auth_admin_off"
    admin.role = "admin"
    await session.commit()

    r = await client.post(
        "/api/v1/demo/simulate_result",
        json={"game": GAME, "metrics": {"cs2_kd_ratio": 1.5}},
        headers=auth_headers("auth_admin_off"),
    )
    assert r.status_code == 404, r.text


async def test_simulate_result_says_loudly_that_it_is_simulated(
    session, client, simulation_on
):
    """Nobody should ever mistake an injected settlement for a real one."""
    from .conftest import auth_headers

    admin = await create_user(session, username="adminsim")
    admin.auth_id = "auth_admin_sim"
    admin.role = "admin"
    await create_linked_account(
        session,
        admin,
        GAME,
        host_account_id="adminnick",
        profile=cs2_profile("adminnick"),
    )
    await session.commit()

    r = await client.post(
        "/api/v1/demo/simulate_result",
        json={
            "game": GAME,
            "user_id": str(admin.id),
            "metrics": {"cs2_kd_ratio": 1.62, "cs2_adr": 91.3},
            "rounds": 22,
            "won": True,
        },
        headers=auth_headers("auth_admin_sim"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is True
    assert "injected" in body["warning"].lower()
    assert body["host_account_id"] == "adminnick"


async def test_force_settle_rejects_an_unknown_contest(session, client, simulation_on):
    from .conftest import auth_headers

    admin = await create_user(session, username="adminfs")
    admin.auth_id = "auth_admin_fs"
    admin.role = "admin"
    await session.commit()

    r = await client.post(
        "/api/v1/demo/force_settle",
        json={"contest_id": str(uuid.uuid4())},
        headers=auth_headers("auth_admin_fs"),
    )
    assert r.status_code == 404, r.text
