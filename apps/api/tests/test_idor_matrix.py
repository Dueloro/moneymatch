"""Authorization matrix."""

from __future__ import annotations

import uuid

import pytest

from .conftest import auth_headers
from .test_play_endpoints import _queue, setup_player

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"

NO_AUTH_ENDPOINTS = [
    ("GET", f"{V1}/me"),
    ("GET", f"{V1}/wallet"),
    ("POST", f"{V1}/wallet/demo-deposit"),
    ("GET", f"{V1}/links"),
    ("GET", f"{V1}/play/markets"),
    ("POST", f"{V1}/play/queue"),
    ("GET", f"{V1}/play/waiting"),
    ("GET", f"{V1}/pools"),
    ("GET", f"{V1}/tournaments"),
    ("GET", f"{V1}/activity"),
    ("GET", f"{V1}/friends"),
    ("GET", f"{V1}/leaderboard"),
    ("GET", f"{V1}/notifications"),
    ("GET", f"{V1}/challenges/{uuid.uuid4()}"),
    ("GET", f"{V1}/admin/users"),
]


@pytest.mark.parametrize(("method", "path"), NO_AUTH_ENDPOINTS)
async def test_endpoint_requires_auth(client, method: str, path: str) -> None:
    resp = await client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} was reachable without auth"


async def _match_between(client, a_auth: str, b_auth: str) -> str:
    await setup_player(client, a_auth, a_auth.replace("auth_", ""))
    await setup_player(client, b_auth, b_auth.replace("auth_", ""))
    await _queue(client, a_auth)
    r = await _queue(client, b_auth)
    return r.json()["match"]["id"]


async def test_outsider_cannot_read_others_match(client) -> None:
    match_id = await _match_between(client, "auth_idor_a", "auth_idor_b")
    await setup_player(client, "auth_idor_c", "idorc")

    r = await client.get(
        f"{V1}/play/matches/{match_id}", headers=auth_headers("auth_idor_c")
    )
    assert r.status_code == 403
    assert r.json()["code"] == "not_a_player"


async def test_outsider_cannot_confirm_or_decline_others_match(client) -> None:
    match_id = await _match_between(client, "auth_idor_d", "auth_idor_e")
    await setup_player(client, "auth_idor_f", "idorf")

    confirm = await client.post(
        f"{V1}/play/matches/{match_id}/confirm", headers=auth_headers("auth_idor_f")
    )
    decline = await client.post(
        f"{V1}/play/matches/{match_id}/decline", headers=auth_headers("auth_idor_f")
    )
    assert confirm.status_code == 403
    assert decline.status_code == 403


async def test_unknown_match_id_is_not_found(client) -> None:
    await setup_player(client, "auth_idor_g", "idorg")
    r = await client.get(
        f"{V1}/play/matches/{uuid.uuid4()}", headers=auth_headers("auth_idor_g")
    )
    assert r.status_code == 404


async def test_notifications_do_not_leak_across_users(client) -> None:
    await _match_between(client, "auth_idor_h", "auth_idor_i")
    await setup_player(client, "auth_idor_j", "idorj")

    involved = await client.get(
        f"{V1}/notifications", headers=auth_headers("auth_idor_h")
    )
    outsider = await client.get(
        f"{V1}/notifications", headers=auth_headers("auth_idor_j")
    )
    assert involved.json()["unread"] >= 1
    assert outsider.json()["unread"] == 0
    assert outsider.json()["items"] == []


async def test_wallet_is_caller_scoped(client) -> None:
    await setup_player(client, "auth_idor_k", "idork")
    await setup_player(client, "auth_idor_l", "idorl")
    await client.post(
        f"{V1}/wallet/demo-deposit",
        json={"amount_preset_cents": 5_000},
        headers=auth_headers("auth_idor_k"),
    )
    b_wallet = await client.get(f"{V1}/wallet", headers=auth_headers("auth_idor_l"))
    assert b_wallet.json()["available_cents"] == 100_000
