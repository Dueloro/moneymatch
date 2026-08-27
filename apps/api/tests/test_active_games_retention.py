"""Removing a game from the play set is a play-set edit only — it must never
delete the linked account or its history (C4 data-retention guarantee)."""

from __future__ import annotations

from sqlalchemy import func, select

from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.user import User

from .conftest import auth_headers
from .factories import create_linked_account, cs2_profile

V1 = "/api/v1"


async def test_removing_active_game_keeps_the_linked_account(client, session):
    auth = "auth_ag_retain"
    # Provision, link CS2, and put it in the play set.
    await client.get(f"{V1}/me", headers=auth_headers(auth))
    user = await session.scalar(select(User).where(User.auth_id == auth))
    user_id = user.id
    link = await create_linked_account(
        session, user, "cs2.steam", host_account_id="h_retain", profile=cs2_profile("r")
    )
    link_id = link.id
    await session.commit()

    await client.patch(
        f"{V1}/me",
        json={"active_games": ["chess.lichess", "cs2.steam"]},
        headers=auth_headers(auth),
    )

    # Remove CS2 from the play set.
    r = await client.patch(
        f"{V1}/me",
        json={"active_games": ["chess.lichess"]},
        headers=auth_headers(auth),
    )
    assert r.status_code == 200
    assert r.json()["user"]["active_games"] == ["chess.lichess"]

    # The linked account row is untouched — nothing was deleted.
    session.expire_all()
    still_there = await session.get(LinkedAccount, link_id)
    assert still_there is not None
    assert still_there.status != "unbound"
    count = await session.scalar(
        select(func.count())
        .select_from(LinkedAccount)
        .where(LinkedAccount.user_id == user_id, LinkedAccount.game == "cs2.steam")
    )
    assert count == 1
