"""Demo real-account handle swap — `linking_service.rebind` + `/demo/relink`.

The shared demo user is auto-linked to every game with a placeholder handle;
`rebind` swaps that for a real handle by soft-unbinding the old link (freeing the
partial-unique slot while keeping its FK history) and binding the new one, all in
one transaction. Host APIs are respx-mocked (no live network).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from moneymatch_api.config import get_settings
from moneymatch_api.constants import DEMO_AUTH_ID, DEMO_USERNAME
from moneymatch_api.main import create_app
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.user import User
from moneymatch_api.services import linking_service

from . import factories
from .conftest import auth_headers

CHESS = "chess.lichess"
LI = "https://lichess.org/api/user"


@pytest_asyncio.fixture
async def demo_client() -> AsyncIterator[AsyncClient]:
    """An ASGI client whose app has the demo router mounted (demo_login on)."""
    settings = get_settings().model_copy(update={"demo_login_enabled": True})
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_demo_user_with_placeholder(session, game=CHESS) -> User:
    """The shared demo user, auto-linked to `game` with the 'demo' placeholder."""
    user = User(
        auth_id=DEMO_AUTH_ID,
        username=DEMO_USERNAME,
        email="demo@dueloro.com",
        residence_state="MA",
        dob_attested_18plus=True,
    )
    session.add(user)
    await session.flush()
    await factories.create_linked_account(
        session, user, game, host_account_id=f"{game}_{DEMO_USERNAME}"
    )
    await session.commit()
    return user


def _lichess_user(username="magnus", rating=2800):
    return {
        "id": username.lower(),
        "username": username,
        "url": f"https://lichess.org/@/{username}",
        "createdAt": 1_300_000_000_000,
        "perfs": {"blitz": {"rating": rating, "games": 500}},
        "count": {"rated": 500, "win": 300, "draw": 50, "loss": 150},
    }


@respx.mock
async def test_rebind_swaps_existing_link_to_new_handle(session):
    """rebind soft-unbinds the old binding and binds the new real handle."""
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user("magnus"))
    )
    respx.get(f"{LI}/hikaru").mock(
        return_value=httpx.Response(200, json=_lichess_user("hikaru"))
    )
    user = await factories.create_user(session)
    await linking_service.bind(session, user, CHESS, "magnus")

    link = await linking_service.rebind(session, user, CHESS, "hikaru")

    # The live binding is now the real handle.
    assert link.host_username == "hikaru"
    assert link.status == "active"
    live = await linking_service.get_link(session, user.id, CHESS)
    assert live is not None and live.host_username == "hikaru"

    # The old binding is retained but soft-unbound (kept for FK history).
    rows = list(
        await session.scalars(
            select(LinkedAccount).where(
                LinkedAccount.user_id == user.id, LinkedAccount.game == CHESS
            )
        )
    )
    statuses = {r.host_username: r.status for r in rows}
    assert statuses == {"magnus": "unbound", "hikaru": "active"}


@respx.mock
async def test_rebind_with_no_existing_link_just_binds(session):
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user("magnus"))
    )
    user = await factories.create_user(session)

    link = await linking_service.rebind(session, user, CHESS, "magnus")

    assert link.host_username == "magnus" and link.status == "active"


def _game(resp, game):
    return next(g for g in resp["games"] if g["game"] == game)


@respx.mock
async def test_demo_relink_swaps_placeholder_to_real(demo_client, session):
    """The demo user points a game at a real handle; live verify + snapshot."""
    await _seed_demo_user_with_placeholder(session, CHESS)
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user("magnus"))
    )

    r = await demo_client.post(
        "/api/v1/demo/relink",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers(DEMO_AUTH_ID, email="demo@dueloro.com"),
    )

    assert r.status_code == 200, r.text
    chess = _game(r.json(), CHESS)
    assert chess["status"] == "LINKED"
    assert chess["host_username"] == "magnus"
    assert chess["profile"]["formats"][0]["rating"] == 2800


@respx.mock
async def test_relink_rejected_for_non_demo_user(demo_client, session):
    """A normal (non-demo) user cannot use the demo relink seam."""
    respx.get(f"{LI}/magnus").mock(
        return_value=httpx.Response(200, json=_lichess_user("magnus"))
    )
    r = await demo_client.post(
        "/api/v1/demo/relink",
        json={"game": CHESS, "username": "magnus"},
        headers=auth_headers("not-the-demo-user"),
    )
    assert r.status_code == 404


@respx.mock
async def test_bad_handle_rolls_back_and_keeps_old_link(demo_client, session):
    """An unknown handle leaves the original placeholder binding intact."""
    await _seed_demo_user_with_placeholder(session, CHESS)
    respx.get(f"{LI}/ghost").mock(return_value=httpx.Response(404))

    r = await demo_client.post(
        "/api/v1/demo/relink",
        json={"game": CHESS, "username": "ghost"},
        headers=auth_headers(DEMO_AUTH_ID, email="demo@dueloro.com"),
    )
    assert r.status_code == 404

    # The placeholder binding is still the live link.
    g = await demo_client.get(
        "/api/v1/links", headers=auth_headers(DEMO_AUTH_ID, email="demo@dueloro.com")
    )
    assert _game(g.json(), CHESS)["status"] == "LINKED"
    assert _game(g.json(), CHESS)["host_username"] == f"{CHESS}_{DEMO_USERNAME}"
