"""`/admin/contests` — list/detail money trail + the resettle/void money fixes.

The required Phase-6 properties: resettle is idempotent (no double-pay) and void
refunds exactly the escrowed amounts with the invariant intact. Reuses the
settlement-worker test harness (adapter-mocked grading).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.adapters import registry
from moneymatch_api.models.user import User
from moneymatch_api.services import reconciliation_service, wallet_service

from .conftest import auth_headers, new_sessionmaker
from .test_settlement_worker import FakeCS2Adapter, _game, setup_active_cs2

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


async def _balance(sm, user_id):
    async with sm() as s:
        w = await wallet_service.get_wallet(s, user_id)
        return w.available_cents, w.escrow_cents


async def test_contest_list_and_detail_money_trail(client, monkeypatch):
    await _admin(client)
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)
    # Settle it via the worker so there's a full money trail.
    from moneymatch_api.workers import settlement_worker

    await settlement_worker.run_cycle(sm, now=info["matched_at"] + timedelta(seconds=5))

    r = await client.get(
        f"{V1}/admin/contests",
        params={"ref_type": "match"},
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    assert any(c["ref_id"] == str(info["match_id"]) for c in r.json()["contests"])

    r = await client.get(
        f"{V1}/admin/contests/match/{info['match_id']}",
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "SETTLED"
    assert body["reconciliation"]["ok"] is True
    # Money trail: escrow holds + a payout + a rake platform row.
    types = {row["entry_type"] for row in body["ledger"]}
    assert {"escrow_hold", "payout"} <= types
    assert any(p["account"] == "platform:rake" for p in body["platform_ledger"])


async def test_resettle_is_idempotent(client, monkeypatch):
    await _admin(client)
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    # First resettle grades + settles: winner +$18.
    r = await client.post(
        f"{V1}/admin/matches/{info['match_id']}/resettle",
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "SETTLED"
    assert await _balance(sm, info["a"]) == (10800, 0)

    # Second resettle on the now-terminal match is a no-op — no double pay.
    r = await client.post(
        f"{V1}/admin/matches/{info['match_id']}/resettle",
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    assert await _balance(sm, info["a"]) == (10800, 0)  # unchanged


async def test_void_refunds_exactly_and_reconciles(client):
    await _admin(client)
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    # Both escrowed $10 in the ACTIVE match.
    assert await _balance(sm, info["a"]) == (9000, 1000)

    r = await client.post(
        f"{V1}/admin/matches/{info['match_id']}/void",
        headers=auth_headers("auth_admin"),
        json={"reason": "operator void"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "CANCELED"

    # Exact refund of the escrowed entries, zero rake, invariant holds.
    assert await _balance(sm, info["a"]) == (10000, 0)
    assert await _balance(sm, info["b"]) == (10000, 0)
    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", info["match_id"])
        assert recon.ok and recon.totals["rake"] == 0
        assert (await reconciliation_service.check_all(s)).ok


async def test_void_terminal_match_rejected(client, monkeypatch):
    await _admin(client)
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    monkeypatch.setattr(
        registry,
        "get",
        lambda gid: FakeCS2Adapter(
            {
                info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
                info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
            }
        ),
    )
    from moneymatch_api.workers import settlement_worker

    await settlement_worker.run_cycle(sm, now=info["matched_at"] + timedelta(seconds=5))

    r = await client.post(
        f"{V1}/admin/matches/{info['match_id']}/void",
        headers=auth_headers("auth_admin"),
        json={"reason": "too late"},
    )
    assert r.status_code == 409
