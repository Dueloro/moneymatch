"""First-match funnel: /me.getting_started progress signal."""

from __future__ import annotations

from .conftest import auth_headers
from .factories import create_linked_account, cs2_profile

V1 = "/api/v1"


async def test_fresh_user_has_empty_getting_started(client):
    r = await client.get(f"{V1}/me", headers=auth_headers("auth_gs_fresh"))
    gs = r.json()["getting_started"]
    assert gs == {
        "picked_games": False,
        "linked_game": False,
        "placed_wager": False,
        "complete": False,
    }


async def test_progress_advances_with_games_and_link(client, session):
    from sqlalchemy import select

    from moneymatch_api.models.user import User

    # Provision via the API, then pick games + link an account.
    await client.get(f"{V1}/me", headers=auth_headers("auth_gs_prog"))
    await client.patch(
        f"{V1}/me",
        json={"active_games": ["cs2.steam"]},
        headers=auth_headers("auth_gs_prog"),
    )
    user = await session.scalar(select(User).where(User.auth_id == "auth_gs_prog"))
    await create_linked_account(
        session, user, "cs2.steam", host_account_id="h_gs", profile=cs2_profile("gs")
    )
    await session.commit()

    gs = (await client.get(f"{V1}/me", headers=auth_headers("auth_gs_prog"))).json()[
        "getting_started"
    ]
    assert gs["picked_games"] is True
    assert gs["linked_game"] is True
    assert gs["placed_wager"] is False  # hasn't wagered yet
    assert gs["complete"] is False
