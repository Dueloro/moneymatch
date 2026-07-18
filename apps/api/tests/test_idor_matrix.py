"""Authorization matrix (10-phase-7 §2).

Two guarantees the money model depends on:

1. **Every router requires auth.** No consumer endpoint is reachable without a
   verified Supabase JWT — an unauthenticated request is rejected before any
   handler runs.
2. **Object-level access control (no IDOR).** A user cannot read or mutate
   another user's contest, and per-user surfaces (wallet, notifications) never
   leak across accounts. Ids are not capabilities.
"""

from __future__ import annotations

import uuid

import pytest

from .conftest import auth_headers
from .test_play_endpoints import _queue, setup_player

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"

# One representative endpoint per consumer router — the auth gate is a router
# dependency, so hitting one path per router proves the whole surface.
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
    """Queue two linked players and return the match id they were paired into."""
    await setup_player(client, a_auth, a_auth.replace("auth_", ""))
    await setup_player(client, b_auth, b_auth.replace("auth_", ""))
    await _queue(client, a_auth)
    r = await _queue(client, b_auth)
    return r.json()["match"]["id"]


async def test_outsider_cannot_read_others_match(client) -> None:
    match_id = await _match_between(client, "auth_idor_a", "auth_idor_b")
    await setup_player(client, "auth_idor_c", "idorc")  # uninvolved third user

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
    # Pairing fans out a match_found notification to both participants only.
    await _match_between(client, "auth_idor_h", "auth_idor_i")
    await setup_player(client, "auth_idor_j", "idorj")  # uninvolved

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
    # A's deposit is invisible to B; the wallet endpoint has no id to tamper with.
    await setup_player(client, "auth_idor_k", "idork")
    await setup_player(client, "auth_idor_l", "idorl")
    await client.post(
        f"{V1}/wallet/demo-deposit",
        json={"amount_preset_cents": 5_000},
        headers=auth_headers("auth_idor_k"),
    )
    b_wallet = await client.get(f"{V1}/wallet", headers=auth_headers("auth_idor_l"))
    # B only ever sees B's own signup grant, never A's deposit.
    assert b_wallet.json()["available_cents"] == 100_000
