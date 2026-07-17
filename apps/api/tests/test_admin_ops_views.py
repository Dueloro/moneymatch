"""`/admin/queue`, `/admin/reconciliation`, `/admin/risk` — the read-only ops views."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.user import User

from .conftest import auth_headers, new_sessionmaker
from .test_matchmaking import cs2_player, enq_cs2

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


async def test_queue_view_reports_waiting_depth(client):
    await _admin(client)
    sm = new_sessionmaker()
    async with sm() as s:
        a = await cs2_player(s, "waiter", mu=1.0, sigma=0.3)
        await enq_cs2(s, a)  # one waiting ticket
        await s.commit()

    r = await client.get(f"{V1}/admin/queue", headers=auth_headers("auth_admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["waiting"] >= 1
    assert any(d["waiting"] >= 1 for d in body["depth"])


async def test_reconciliation_clean_book(client):
    await _admin(client)
    r = await client.get(
        f"{V1}/admin/reconciliation", headers=auth_headers("auth_admin")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["solvency_ok"] is True
    assert body["contest_violations"] == []
    # Worker heartbeat has never been written in this test → stale.
    assert body["worker"]["stale"] is True


async def test_risk_view_and_clear_flag(client):
    admin_id = await _admin(client)
    sm = new_sessionmaker()
    from moneymatch_api.models.risk import RiskFlag

    # Seed a user with an open sandbagging flag.
    async with sm() as s:
        flagged = await cs2_player(s, "tanker", mu=1.0, sigma=0.3)
        flag = RiskFlag(
            user_id=flagged.id,
            game="cs2.faceit",
            metric="cs2_kd_ratio",
            kind="sandbagging",
            detail={"z": -2.0},
        )
        s.add(flag)
        await s.commit()
        flag_id = flag.id

    r = await client.get(f"{V1}/admin/risk", headers=auth_headers("auth_admin"))
    assert r.status_code == 200, r.text
    flags = r.json()["flags"]
    assert any(f["id"] == str(flag_id) for f in flags)

    # Clear it → audited, and it drops off the open queue.
    r = await client.post(
        f"{V1}/admin/risk/flags/{flag_id}/clear", headers=auth_headers("auth_admin")
    )
    assert r.status_code == 200, r.text

    async with sm() as s:
        refreshed = await s.get(RiskFlag, flag_id)
        assert refreshed.resolved is True
        from moneymatch_api.models.admin_audit import AdminAudit

        audited = await s.scalar(
            select(AdminAudit).where(
                AdminAudit.action == "risk_flag.clear",
                AdminAudit.admin_id == admin_id,
            )
        )
        assert audited is not None
