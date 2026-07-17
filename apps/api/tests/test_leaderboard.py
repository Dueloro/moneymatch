"""Leaderboard (08-phase-5 · tests): the qualification threshold, ROI math from
ledger fixtures, and the rolling-window boundary. Fixtures write the exact ledger
row shapes a settlement produces (escrow_release consumes a stake; payout credits
a prize; refund is net-neutral and excluded)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from moneymatch_api.models.wallet import LedgerEntry
from moneymatch_api.services import leaderboard as lb

from .factories import create_user, create_wallet

pytestmark = pytest.mark.asyncio

ENTRY = 1_000
PRIZE = 1_800  # $18 on a $10 stake (10% rake)


async def _row(session, wallet_id, entry_type, amount, escrow_delta, ref, when=None):
    kwargs = dict(
        wallet_id=wallet_id,
        entry_type=entry_type,
        amount_cents=amount,
        escrow_delta_cents=escrow_delta,
        ref_type="match",
        ref_id=ref,
        balance_after_cents=0,
    )
    if when is not None:
        kwargs["created_at"] = when
    session.add(LedgerEntry(**kwargs))
    await session.flush()


async def _win(session, wallet_id, *, when=None):
    ref = uuid.uuid4()
    await _row(session, wallet_id, "escrow_release", 0, -ENTRY, ref, when)
    await _row(session, wallet_id, "payout", PRIZE, 0, ref, when)


async def _loss(session, wallet_id, *, when=None):
    ref = uuid.uuid4()
    await _row(session, wallet_id, "escrow_release", 0, -ENTRY, ref, when)


async def _refund(session, wallet_id, *, when=None):
    ref = uuid.uuid4()
    await _row(session, wallet_id, "refund", ENTRY, -ENTRY, ref, when)


async def _player(session, name):
    user = await create_user(session, username=name)
    wallet = await create_wallet(session, user)
    return user, wallet


async def test_qualification_threshold(session):
    user, wallet = await _player(session, "alice")
    await _loss(session, wallet.id)
    await _loss(session, wallet.id)  # only 2 settled → not qualified

    board = await lb.compute(session, user)
    assert board.you.qualified is False
    assert board.you.contests == 2
    assert board.you.contests_needed == 1
    assert board.rows == []

    await _win(session, wallet.id)  # 3rd contest → qualifies
    board = await lb.compute(session, user)
    assert board.you.qualified is True
    assert board.you.contests == 3
    assert board.you.contests_needed == 0


async def test_roi_math_and_ranking(session):
    a, wa = await _player(session, "alice")
    b, wb = await _player(session, "bob")
    # alice: 1 win + 2 losses → net −1200 on 3000 staked = −40%.
    await _win(session, wa.id)
    await _loss(session, wa.id)
    await _loss(session, wa.id)
    # bob: 3 wins → net +2400 on 3000 staked = +80%.
    await _win(session, wb.id)
    await _win(session, wb.id)
    await _win(session, wb.id)

    board = await lb.compute(session, a)
    assert [r.username for r in board.rows] == ["bob", "alice"]  # ROI desc
    bob, alice = board.rows
    assert bob.rank == 1 and alice.rank == 2
    assert bob.roi_bps == 8000 and bob.net_cents == 2400 and bob.staked_cents == 3000
    assert alice.roi_bps == -4000 and alice.net_cents == -1200
    assert alice.is_you is True and bob.is_you is False


async def test_refunds_and_friendlies_excluded(session):
    """Refunded stakes (pushes, cancels, friendlies) never enter staked or net."""
    user, wallet = await _player(session, "alice")
    await _win(session, wallet.id)
    await _loss(session, wallet.id)
    await _loss(session, wallet.id)
    await _refund(session, wallet.id)  # excluded
    await _refund(session, wallet.id)  # excluded

    board = await lb.compute(session, user)
    row = board.you.row
    assert row.contests == 3  # refunds didn't add contests
    assert row.staked_cents == 3000
    assert row.net_cents == -1200


async def test_rolling_window_boundary(session):
    user, wallet = await _player(session, "alice")
    now = datetime.now(UTC)
    # 3 recent contests qualify; an old win outside the window is ignored.
    await _win(session, wallet.id)
    await _loss(session, wallet.id)
    await _loss(session, wallet.id)
    await _win(session, wallet.id, when=now - timedelta(days=45))

    board = await lb.compute(session, user, now=now)
    row = board.you.row
    assert row.contests == 3  # the 45-day-old win is outside the 30-day window
    assert row.staked_cents == 3000
    assert row.net_cents == -1200
