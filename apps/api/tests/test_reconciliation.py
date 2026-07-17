"""reconciliation_service: per-contest conservation, global solvency, drift
detection, and a concurrent demo-op storm (Phase 1 exit criterion)."""

from __future__ import annotations

import asyncio
import random
import uuid

from sqlalchemy import select, text

from moneymatch_api.models.user import User
from moneymatch_api.services import reconciliation_service as recon
from moneymatch_api.services import wallet_service as ws

from .conftest import auth_headers, new_sessionmaker
from .factories import create_user, create_wallet


async def _settle_h2h(session, winner, loser, entry, prize, rake_cents, ref):
    for p in (winner, loser):
        await ws.escrow_hold(session, p.id, entry, ref_type="match", ref_id=ref)
    for p in (winner, loser):
        await ws.escrow_release(session, p.id, entry, ref_type="match", ref_id=ref)
    await ws.payout(session, winner.id, prize, ref_type="match", ref_id=ref)
    await ws.rake(session, rake_cents, ref_type="match", ref_id=ref)


async def test_check_settled_match_reconciles(session):
    a = await create_user(session)
    b = await create_user(session)
    await create_wallet(session, a, available_cents=100_00)
    await create_wallet(session, b, available_cents=100_00)
    ref = uuid.uuid4()
    await _settle_h2h(session, a, b, 10_00, 18_00, 2_00, ref)

    result = await recon.check(session, "match", ref)
    assert result.ok
    assert result.totals["still_held"] == 0
    assert result.totals["entries"] == 20_00
    assert result.totals["distributed"] + result.totals["rake"] == 20_00


async def test_check_push_reconciles_zero_rake(session):
    a = await create_user(session)
    b = await create_user(session)
    await create_wallet(session, a, available_cents=100_00)
    await create_wallet(session, b, available_cents=100_00)
    ref = uuid.uuid4()
    for p in (a, b):
        await ws.escrow_hold(session, p.id, 10_00, ref_type="match", ref_id=ref)
    for p in (a, b):
        await ws.refund(session, p.id, 10_00, ref_type="match", ref_id=ref)

    result = await recon.check(session, "match", ref)
    assert result.ok
    assert result.totals["rake"] == 0
    assert result.totals["distributed"] == 20_00


async def test_check_holds_identity_while_in_flight(session):
    a = await create_user(session)
    await create_wallet(session, a, available_cents=100_00)
    ref = uuid.uuid4()
    await ws.escrow_hold(session, a.id, 10_00, ref_type="match", ref_id=ref)
    result = await recon.check(session, "match", ref)
    assert result.ok  # identity holds even unsettled
    assert result.totals["still_held"] == 10_00


async def test_check_all_solvency_after_ops(client, session):
    for sub in ("r1", "r2"):
        await client.get("/api/v1/me", headers=auth_headers(sub))
    u1 = await session.scalar(select(User).where(User.auth_id == "r1"))
    await ws.demo_deposit(session, u1.id, 25_00)
    await ws.demo_withdrawal(session, u1.id, 5_00)
    await ws.escrow_hold(session, u1.id, 40_00, ref_type="match", ref_id=uuid.uuid4())
    await session.commit()

    result = await recon.check_all(session)
    assert result.ok, result.violations


async def test_check_all_detects_cache_drift(client, session):
    await client.get("/api/v1/me", headers=auth_headers("driftguy"))
    u = await session.scalar(select(User).where(User.auth_id == "driftguy"))
    # Corrupt the cached balance directly (wallets are not append-only).
    await session.execute(
        text(
            "UPDATE wallets SET available_cents = available_cents + 500 "
            "WHERE user_id = :uid"
        ),
        {"uid": u.id},
    )
    await session.commit()

    result = await recon.check_all(session)
    assert not result.ok
    assert any("drift" in v or "solvency" in v for v in result.violations)


async def test_check_all_after_concurrent_storm(client, session):
    subs = [f"storm_{i}" for i in range(6)]
    for sub in subs:
        await client.get("/api/v1/me", headers=auth_headers(sub))
    users = list(await session.scalars(select(User).where(User.auth_id.in_(subs))))
    await session.commit()

    sm = new_sessionmaker()

    async def churn(user_id, seed):
        rng = random.Random(seed)
        for _ in range(15):
            async with sm() as s:
                op = rng.choice(["deposit", "withdraw", "hold", "hold_refund"])
                amt = rng.randint(1_00, 20_00)
                try:
                    if op == "deposit":
                        await ws.demo_deposit(s, user_id, amt)
                    elif op == "withdraw":
                        await ws.demo_withdrawal(s, user_id, amt)
                    elif op == "hold":
                        await ws.escrow_hold(
                            s, user_id, amt, ref_type="match", ref_id=uuid.uuid4()
                        )
                    else:
                        ref = uuid.uuid4()
                        await ws.escrow_hold(
                            s, user_id, amt, ref_type="match", ref_id=ref
                        )
                        await ws.refund(s, user_id, amt, ref_type="match", ref_id=ref)
                    await s.commit()
                except ws.WalletError:
                    await s.rollback()

    # Two concurrent workers per user hammer the same wallets in parallel.
    tasks = []
    for i, u in enumerate(users):
        tasks.append(churn(u.id, seed=i))
        tasks.append(churn(u.id, seed=100 + i))
    await asyncio.gather(*tasks)

    result = await recon.check_all(session)
    assert result.ok, result.violations
