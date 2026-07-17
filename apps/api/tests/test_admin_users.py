"""`/admin/users` — search, detail, freeze/unfreeze, adjust, unbind, ledger.

Covers the operator loop from exit criterion 1: find a user, see their money
trail, and fix things — all audited.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from moneymatch_api.models.admin_audit import AdminAudit
from moneymatch_api.models.user import User
from moneymatch_api.services import wallet_service

from . import factories
from .conftest import auth_headers, new_sessionmaker

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


async def _admin(client, auth_id="auth_admin", name="admin1"):
    await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        user.role = "admin"
        await s.commit()
        return user.id


async def _seed_user(username="target", available=5_000):
    sm = new_sessionmaker()
    async with sm() as s:
        user = await factories.create_user(s, username=username)
        await factories.create_wallet(s, user, available_cents=available)
        await factories.create_limit(s, user)
        await s.commit()
        return user.id


async def test_search_and_detail(client):
    await _admin(client)
    uid = await _seed_user(username="searchme", available=7_777)

    r = await client.get(
        f"{V1}/admin/users",
        params={"q": "searchme"},
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    users = r.json()["users"]
    assert any(u["username"] == "searchme" for u in users)

    r = await client.get(f"{V1}/admin/users/{uid}", headers=auth_headers("auth_admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available_cents"] == 7_777
    assert body["limits"]["max_concurrent_contests"] == 3
    assert body["linked_accounts"] == []
    assert body["contests"] == []


async def test_freeze_unfreeze_audited(client):
    await _admin(client)
    uid = await _seed_user(username="freezeme")

    r = await client.post(
        f"{V1}/admin/users/{uid}/freeze", headers=auth_headers("auth_admin")
    )
    assert r.status_code == 200
    assert r.json()["status"] == "frozen"

    r = await client.post(
        f"{V1}/admin/users/{uid}/unfreeze", headers=auth_headers("auth_admin")
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    sm = new_sessionmaker()
    async with sm() as s:
        actions = set(
            await s.scalars(
                select(AdminAudit.action).where(AdminAudit.target == str(uid))
            )
        )
    assert {"user.freeze", "user.unfreeze"} <= actions


async def test_manual_adjustment_credits_and_audits(client):
    await _admin(client)
    uid = await _seed_user(username="adjustme", available=1_000)

    r = await client.post(
        f"{V1}/admin/users/{uid}/adjust",
        headers=auth_headers("auth_admin"),
        json={"amount_cents": 2_500, "reason": "goodwill credit"},
    )
    assert r.status_code == 200, r.text

    sm = new_sessionmaker()
    async with sm() as s:
        wallet = await wallet_service.get_wallet(s, uid)
        assert wallet.available_cents == 3_500
        n_audit = await s.scalar(
            select(func.count())
            .select_from(AdminAudit)
            .where(AdminAudit.action == "ledger.adjust")
        )
    assert n_audit == 1


async def test_adjustment_requires_reason(client):
    await _admin(client)
    uid = await _seed_user(username="noreason")
    r = await client.post(
        f"{V1}/admin/users/{uid}/adjust",
        headers=auth_headers("auth_admin"),
        json={"amount_cents": 100, "reason": ""},
    )
    assert r.status_code == 422


async def test_force_unbind_removes_binding(client):
    await _admin(client)
    sm = new_sessionmaker()
    async with sm() as s:
        user = await factories.create_user(s, username="linked")
        await factories.create_wallet(s, user)
        link = await factories.create_linked_account(s, user, "chess.lichess")
        await s.commit()
        link_id = link.id

    r = await client.post(
        f"{V1}/admin/linked-accounts/{link_id}/unbind",
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text

    async with sm() as s:
        from moneymatch_api.models.linked_account import LinkedAccount

        gone = await s.get(LinkedAccount, link_id)
        assert gone is None


async def test_ledger_endpoint_returns_rows(client):
    await _admin(client)
    uid = await _seed_user(username="ledgerme", available=1_000)
    # Post an adjustment so there is at least one ledger row.
    await client.post(
        f"{V1}/admin/users/{uid}/adjust",
        headers=auth_headers("auth_admin"),
        json={"amount_cents": 500, "reason": "seed row"},
    )
    r = await client.get(
        f"{V1}/admin/ledger",
        params={"user": str(uid)},
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert any(e["entry_type"] == "adjustment" for e in entries)
