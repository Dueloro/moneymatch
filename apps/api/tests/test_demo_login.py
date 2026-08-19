"""`POST /demo/login` on a **fresh** database — the front door of the demo.

Nothing in the suite called this endpoint. The one test that went near its
setup (`test_demo_reset.py`) monkeypatches `_ensure_demo_fixture` and
`_ensure_demo_history` to no-ops, so the two functions that actually build a
demo account were not merely untested — they were switched off before running.

The bug that exposed the gap: `_ensure_demo_fixture` deliberately does **not**
create a `cs2.steam` link, because a SteamID64 is the one identity that cannot
be fabricated and a placeholder would occupy the slot the player's real Steam
account has to bind into. `_ensure_demo_history` then tried to seed sample CS2
matches against that non-existent link and raised `KeyError: 'cs2.steam'`.

It only ever fired on a database with no sample history. Production had rows
left from the FACEIT era — when a placeholder CS2 link *was* allowed — so the
idempotency guard short-circuited and nobody hit it for months. Restoring the
database from empty removed the cover and every demo sign-in 500'd.

These tests run against a fresh schema by construction, which is exactly the
condition that was never covered.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from moneymatch_api.config import get_settings
from moneymatch_api.constants import (
    DEMO_AUTH_ID,
    GAME_CS2_STEAM,
    GAME_PUBG_STEAM,
)
from moneymatch_api.main import create_app
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.models.user import User


@pytest_asyncio.fixture
async def demo_client() -> AsyncIterator[AsyncClient]:
    settings = get_settings().model_copy(update={"demo_login_enabled": True})
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _demo_user(session) -> User | None:
    return await session.scalar(select(User).where(User.auth_id == DEMO_AUTH_ID))


async def test_demo_login_succeeds_on_a_fresh_database(demo_client):
    """The regression test. This is the request that returned 500 in production."""
    r = await demo_client.post("/api/v1/demo/login")
    assert r.status_code == 200, (
        f"demo login failed with {r.status_code}: {r.text}. This is the front "
        "door of the demo — if it 500s, nobody can get in."
    )
    body = r.json()
    assert body["access_token"]
    assert body["token_type"]


async def test_demo_login_is_idempotent(demo_client, session):
    """Signing in twice must not double-provision or crash the second time."""
    first = await demo_client.post("/api/v1/demo/login")
    second = await demo_client.post("/api/v1/demo/login")
    assert first.status_code == 200
    assert second.status_code == 200

    users = list(
        await session.scalars(select(User).where(User.auth_id == DEMO_AUTH_ID))
    )
    assert len(users) == 1, "demo login must reuse the shared demo user"


async def test_demo_user_never_gets_a_fabricated_steam_link(demo_client, session):
    """The invariant that caused the crash, asserted so it cannot be 'fixed' wrongly.

    The tempting fix is to give the demo a placeholder CS2 link. That must never
    happen: a SteamID64 is vouched for by Steam alone, and a fake one would sit
    in the slot the player's real account needs, blocking the genuine sign-in.
    """
    r = await demo_client.post("/api/v1/demo/login")
    assert r.status_code == 200

    demo = await _demo_user(session)
    cs2_link = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == demo.id,
            LinkedAccount.game == GAME_CS2_STEAM,
        )
    )
    assert cs2_link is None, (
        "the demo user must not be given a placeholder CS2 link — a SteamID64 "
        "cannot be faked, and the placeholder would block the real Steam bind"
    )


async def test_sample_history_is_seeded_only_for_linked_games(demo_client, session):
    """Sample matches appear for games the demo can actually hold an identity on.

    PUBG has a placeholder link, so its samples seed. CS2 has none by design, so
    its samples are skipped rather than crashing the request.
    """
    r = await demo_client.post("/api/v1/demo/login")
    assert r.status_code == 200

    demo = await _demo_user(session)
    games = list(
        await session.scalars(
            select(Match.game)
            .join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(MatchPlayer.user_id == demo.id)
        )
    )
    assert GAME_PUBG_STEAM in games, "PUBG sample history should still seed"
    assert GAME_CS2_STEAM not in games, (
        "CS2 samples must be skipped while the demo holds no CS2 link"
    )


async def test_a_link_present_at_seed_time_is_not_skipped(session):
    """The skip is driven by the link, not hard-coded against CS2.

    Asserted directly on `_ensure_demo_history` because it is a *seed-time*
    decision: the guard at the top of that function makes history a
    once-ever operation, so a link added afterwards does not backfill.

    That matters for what the fix does and does not claim. Skipping keeps the
    request working and leaves the CS2 samples out; it does **not** mean they
    appear later when the demo links Steam. In practice they never will, since
    login always runs before any link exists — and that is fine, because once
    Steam is linked the demo gets real CS2 history from the share-code chain
    rather than fabricated samples.
    """
    from moneymatch_api.constants import DEMO_RESIDENCE_STATE, DEMO_USERNAME
    from moneymatch_api.routers.demo import _ensure_demo_history
    from moneymatch_api.services.user_service import provision_new_user

    demo = User(
        auth_id=DEMO_AUTH_ID,
        username=DEMO_USERNAME,
        email="demo@dueloro.com",
        residence_state=DEMO_RESIDENCE_STATE,
        dob_attested_18plus=True,
    )
    session.add(demo)
    await session.flush()
    await provision_new_user(session, demo)

    # Both links present *before* history is built for the first time.
    for game, host_id in (
        (GAME_PUBG_STEAM, f"{GAME_PUBG_STEAM}_demo"),
        (GAME_CS2_STEAM, "76561198000000123"),
    ):
        session.add(
            LinkedAccount(
                user_id=demo.id,
                game=game,
                host_account_id=host_id,
                host_username="demo",
                profile_snapshot={"username": "demo", "game": game},
            )
        )
    await session.flush()

    await _ensure_demo_history(session, demo)

    games = set(
        await session.scalars(
            select(Match.game)
            .join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(MatchPlayer.user_id == demo.id)
        )
    )
    assert GAME_PUBG_STEAM in games
    assert GAME_CS2_STEAM in games, (
        "a game whose link exists at seed time must not be skipped — the guard "
        "keys off the link, it is not a hard-coded exclusion of CS2"
    )


@pytest.mark.parametrize("attempt", [1, 2, 3])
async def test_demo_login_is_stable_across_repeated_calls(demo_client, attempt):
    """Cheap guard against state that only breaks on the Nth call."""
    r = await demo_client.post("/api/v1/demo/login")
    assert r.status_code == 200
