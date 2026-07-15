"""linked_accounts / raw_payloads schema guarantees (DB-enforced)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.skill import RawPayload

from .factories import create_user


def _link(user_id, *, game="chess.lichess", host_account_id="magnus"):
    return LinkedAccount(
        user_id=user_id,
        game=game,
        host_account_id=host_account_id,
        host_username=host_account_id,
        link_method="username",
        profile_snapshot={"username": host_account_id},
    )


async def test_one_account_per_user_per_game(session):
    user = await create_user(session)
    session.add(_link(user.id, host_account_id="a"))
    await session.flush()
    session.add(_link(user.id, host_account_id="b"))  # same (user, game)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()  # leave the session clean for teardown commit


async def test_host_account_binds_to_one_user(session):
    u1 = await create_user(session)
    u2 = await create_user(session)
    session.add(_link(u1.id, host_account_id="shared"))
    await session.flush()
    session.add(_link(u2.id, host_account_id="shared"))  # same (game, host)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()  # leave the session clean for teardown commit


async def test_second_game_links_independently(session):
    user = await create_user(session)
    session.add(_link(user.id, game="chess.lichess", host_account_id="magnus"))
    session.add(_link(user.id, game="cs2.faceit", host_account_id="s1mple"))
    await session.flush()  # different games → both fine


async def test_raw_payloads_are_append_only(session):
    row = RawPayload(
        source="lichess:user", payload={"a": 1}, content_hash="deadbeef", size_bytes=8
    )
    session.add(row)
    await session.flush()
    with pytest.raises(DBAPIError):
        await session.execute(
            text("UPDATE raw_payloads SET source = 'x' WHERE id = :id"),
            {"id": row.id},
        )
    await session.rollback()  # leave the session clean for teardown commit
