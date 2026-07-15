"""wallet_service: ledger rows, cached balances, invariants, immutability,
and FOR UPDATE concurrency."""

from __future__ import annotations

import asyncio
import random
import uuid

import pytest
from sqlalchemy import func, select, text

from moneymatch_api.models.wallet import LedgerEntry, PlatformLedgerEntry, Wallet
from moneymatch_api.services import wallet_service as ws
from moneymatch_api.services.money_math import split_pot

from .conftest import new_sessionmaker
from .factories import create_user, create_wallet

REF = uuid.uuid4()


async def _ledger(session, wallet_id):
    rows = await session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.wallet_id == wallet_id)
        .order_by(LedgerEntry.created_at, LedgerEntry.id)
    )
    return list(rows.scalars())


async def _reload(session, wallet_id) -> Wallet:
    return await session.get(Wallet, wallet_id, populate_existing=True)


# --------------------------------------------------------------------------- #
# Primitives: ledger rows + balance cache
# --------------------------------------------------------------------------- #


async def test_demo_deposit_credits_and_funds_from_promo(session):
    user = await create_user(session)
    wallet = await create_wallet(session, user, available_cents=0)

    entry = await ws.demo_deposit(session, user.id, 10_00, memo="add funds")

    assert entry.amount_cents == 10_00
    assert entry.balance_after_cents == 10_00
    w = await _reload(session, wallet.id)
    assert w.available_cents == 10_00
    # Promo account went negative by the credited amount (funds the demo money).
    promo = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.account == "platform:promo"
        )
    )
    assert promo == -10_00


async def test_escrow_hold_release_refund_payout_balances(session):
    user = await create_user(session)
    wallet = await create_wallet(session, user, available_cents=100_00)

    await ws.escrow_hold(session, user.id, 10_00, ref_type="match", ref_id=REF)
    w = await _reload(session, wallet.id)
    assert (w.available_cents, w.escrow_cents) == (90_00, 10_00)

    # Refund path returns escrow to available, no P&L.
    await ws.refund(session, user.id, 10_00, ref_type="match", ref_id=REF)
    w = await _reload(session, wallet.id)
    assert (w.available_cents, w.escrow_cents, w.lifetime_net_cents) == (100_00, 0, 0)

    # Consume path: stake lost, lifetime records the loss.
    await ws.escrow_hold(session, user.id, 10_00, ref_type="match", ref_id=REF)
    await ws.escrow_release(session, user.id, 10_00, ref_type="match", ref_id=REF)
    w = await _reload(session, wallet.id)
    assert (w.available_cents, w.escrow_cents, w.lifetime_net_cents) == (
        90_00,
        0,
        -10_00,
    )

    # Payout credits available and records the win.
    await ws.payout(session, user.id, 18_00, ref_type="match", ref_id=REF)
    w = await _reload(session, wallet.id)
    assert (w.available_cents, w.lifetime_net_cents) == (108_00, 8_00)


async def test_balance_after_chain_reconstructs(session):
    user = await create_user(session)
    wallet = await create_wallet(session, user, available_cents=50_00)
    await ws.demo_deposit(session, user.id, 25_00)
    await ws.escrow_hold(session, user.id, 30_00, ref_type="match", ref_id=REF)
    await ws.refund(session, user.id, 30_00, ref_type="match", ref_id=REF)
    await ws.demo_withdrawal(session, user.id, 5_00)

    running = 50_00
    for row in await _ledger(session, wallet.id):
        running += row.amount_cents
        assert row.balance_after_cents == running
    w = await _reload(session, wallet.id)
    assert running == w.available_cents


async def test_rake_books_platform_and_zero_is_noop(session):
    assert await ws.rake(session, 0, ref_type="match", ref_id=REF) is None
    row = await ws.rake(session, 200, ref_type="match", ref_id=REF)
    assert row is not None and row.amount_cents == 200
    total = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.account == "platform:rake"
        )
    )
    assert total == 200


async def test_insufficient_funds_blocks_debit(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=5_00)
    with pytest.raises(ws.InsufficientFundsError):
        await ws.escrow_hold(session, user.id, 10_00, ref_type="match", ref_id=REF)
    with pytest.raises(ws.InsufficientFundsError):
        await ws.demo_withdrawal(session, user.id, 10_00)


async def test_positive_amount_required(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=5_00)
    with pytest.raises(ws.WalletError):
        await ws.demo_deposit(session, user.id, 0)
    with pytest.raises(ws.WalletError):
        await ws.demo_deposit(session, user.id, -100)


# --------------------------------------------------------------------------- #
# Odd-pot settlement reconciles exactly (remainder → rake)
# --------------------------------------------------------------------------- #


async def test_odd_pot_settlement_reconciles(session):
    # 3 entrants × $3.33 = $9.99 pot; 1 clearer takes distributable, rest is rake.
    players = [await create_user(session) for _ in range(3)]
    for p in players:
        await create_wallet(session, p, available_cents=10_00)
    ref = uuid.uuid4()
    for p in players:
        await ws.escrow_hold(session, p.id, 3_33, ref_type="solo_pool", ref_id=ref)

    pot = 3_33 * 3
    split = split_pot(pot, num_winners=1)  # 999 → payout 900, rake 99
    # Consume every stake, pay the winner, book the rake.
    for p in players:
        await ws.escrow_release(session, p.id, 3_33, ref_type="solo_pool", ref_id=ref)
    await ws.payout(
        session, players[0].id, split.payouts_cents[0], ref_type="solo_pool", ref_id=ref
    )
    await ws.rake(session, split.rake_cents, ref_type="solo_pool", ref_id=ref)

    payouts = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.ref_id == ref, LedgerEntry.entry_type.in_(("payout", "refund"))
        )
    )
    rake_total = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.ref_id == ref
        )
    )
    assert payouts + rake_total == pot  # sum(payouts) + rake == sum(entries)


# --------------------------------------------------------------------------- #
# Property-style storm: invariants hold across random operations
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", range(20))
async def test_random_storm_keeps_invariants(session, seed):
    rng = random.Random(seed)
    user = await create_user(session)
    wallet = await create_wallet(session, user, available_cents=100_00)
    ref = uuid.uuid4()
    held = 0  # currently escrowed for `ref`

    for _ in range(40):
        op = rng.choice(["deposit", "withdraw", "hold", "refund", "release", "payout"])
        amt = rng.randint(1, 20_00)
        try:
            if op == "deposit":
                await ws.demo_deposit(session, user.id, amt)
            elif op == "withdraw":
                await ws.demo_withdrawal(session, user.id, amt)
            elif op == "hold":
                await ws.escrow_hold(
                    session, user.id, amt, ref_type="match", ref_id=ref
                )
                held += amt
            elif op == "refund" and held:
                take = rng.randint(1, held)
                await ws.refund(session, user.id, take, ref_type="match", ref_id=ref)
                held -= take
            elif op == "release" and held:
                take = rng.randint(1, held)
                await ws.escrow_release(
                    session, user.id, take, ref_type="match", ref_id=ref
                )
                held -= take
            elif op == "payout":
                await ws.payout(session, user.id, amt, ref_type="match", ref_id=ref)
        except ws.WalletError:
            pass  # rejected ops must leave state untouched

        w = await _reload(session, wallet.id)
        assert w.available_cents >= 0
        assert w.escrow_cents >= 0
        # Cached available equals the sum of its ledger deltas from the $100 start.
        ledger_sum = await session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
                LedgerEntry.wallet_id == wallet.id
            )
        )
        assert w.available_cents == 100_00 + ledger_sum
        # Cached escrow equals the sum of its ledger escrow deltas.
        escrow_sum = await session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.escrow_delta_cents), 0)).where(
                LedgerEntry.wallet_id == wallet.id
            )
        )
        assert w.escrow_cents == escrow_sum


# --------------------------------------------------------------------------- #
# Append-only immutability (DB trigger)
# --------------------------------------------------------------------------- #


async def test_ledger_update_and_delete_rejected(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=10_00)
    entry = await ws.demo_deposit(session, user.id, 5_00)
    await session.commit()

    sm = new_sessionmaker()
    # Each DDL error aborts its transaction, so isolate the two attempts.
    for stmt in (
        "UPDATE ledger_entries SET amount_cents = 999 WHERE id = :i",
        "DELETE FROM ledger_entries WHERE id = :i",
    ):
        async with sm() as s:
            with pytest.raises(Exception) as ei:
                await s.execute(text(stmt), {"i": entry.id})
            assert "append-only" in str(ei.value.__cause__ or ei.value)


# --------------------------------------------------------------------------- #
# Concurrency: two parallel escrows against a balance that covers only one
# --------------------------------------------------------------------------- #


async def test_concurrent_escrow_exactly_one_succeeds(session):
    user = await create_user(session)
    wallet = await create_wallet(session, user, available_cents=10_00)
    await session.commit()

    sm = new_sessionmaker()

    async def try_hold() -> str:
        async with sm() as s:
            try:
                await ws.escrow_hold(
                    s, user.id, 10_00, ref_type="match", ref_id=uuid.uuid4()
                )
                await s.commit()
                return "ok"
            except ws.WalletError:
                await s.rollback()
                return "blocked"

    results = await asyncio.gather(try_hold(), try_hold())
    assert sorted(results) == ["blocked", "ok"]

    w = await _reload(session, wallet.id)
    assert (w.available_cents, w.escrow_cents) == (0, 10_00)
