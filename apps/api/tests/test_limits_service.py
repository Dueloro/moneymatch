"""assert_can_stake: server-side caps at the boundary, status gate, cooldown."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from moneymatch_api.models.wallet import Limit
from moneymatch_api.services import limits_service as ls
from moneymatch_api.services import wallet_service as ws

from .factories import create_limit, create_user, create_wallet


async def _lose(session, user, amount):
    """Realize a loss of `amount`: hold then consume the stake."""
    ref = uuid.uuid4()
    await ws.escrow_hold(session, user.id, amount, ref_type="match", ref_id=ref)
    await ws.escrow_release(session, user.id, amount, ref_type="match", ref_id=ref)


async def test_defaults_created_and_stake_allowed(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=100_00)
    await ls.assert_can_stake(session, user, 10_00)  # no raise
    limit = await ls.get_or_create_limits(session, user.id)
    assert limit.daily_loss_cap_cents == 20_000
    assert limit.daily_entry_cap_cents == 50_000
    assert limit.max_concurrent_contests == 3


async def test_insufficient_funds_blocks(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=5_00)
    with pytest.raises(ls.StakeBlockedError) as ei:
        await ls.assert_can_stake(session, user, 10_00)
    assert ei.value.code == "insufficient_funds"


@pytest.mark.parametrize("status", ["frozen", "self_excluded"])
async def test_non_active_status_blocks(session, status):
    user = await create_user(session, status=status)
    await create_wallet(session, user, available_cents=100_00)
    with pytest.raises(ls.StakeBlockedError) as ei:
        await ls.assert_can_stake(session, user, 10_00)
    assert ei.value.code == "account_not_active"


async def test_daily_entry_cap_at_boundary(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=1_000_00)
    await create_limit(session, user, daily_entry_cap_cents=100_00)
    # Already entered $80; $20 more sits exactly on the cap (allowed).
    await ws.escrow_hold(session, user.id, 80_00, ref_type="match", ref_id=uuid.uuid4())
    await ls.assert_can_stake(session, user, 20_00)
    # One cent over the cap is blocked.
    with pytest.raises(ls.StakeBlockedError) as ei:
        await ls.assert_can_stake(session, user, 20_01)
    assert ei.value.code == "daily_entry_cap_exceeded"


async def test_daily_loss_cap_at_boundary(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=1_000_00)
    await create_limit(session, user, daily_loss_cap_cents=50_00)
    await _lose(session, user, 30_00)  # $30 realized loss → $20 headroom
    await ls.assert_can_stake(session, user, 20_00)
    with pytest.raises(ls.StakeBlockedError) as ei:
        await ls.assert_can_stake(session, user, 20_01)
    assert ei.value.code == "daily_loss_cap_exceeded"


async def test_winnings_offset_loss_headroom(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=1_000_00)
    await create_limit(session, user, daily_loss_cap_cents=50_00)
    await _lose(session, user, 40_00)
    # A payout in the window nets down the realized loss, restoring headroom.
    await ws.payout(session, user.id, 30_00, ref_type="match", ref_id=uuid.uuid4())
    # Net loss now $10 → $40 headroom; a $40 stake is allowed.
    await ls.assert_can_stake(session, user, 40_00)


async def test_concurrent_contest_cap(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=1_000_00)
    await create_limit(session, user, max_concurrent_contests=2)
    for _ in range(2):
        await ws.escrow_hold(
            session, user.id, 1_00, ref_type="match", ref_id=uuid.uuid4()
        )
    with pytest.raises(ls.StakeBlockedError) as ei:
        await ls.assert_can_stake(session, user, 1_00)
    assert ei.value.code == "concurrent_contests_exceeded"


async def test_released_contest_frees_a_slot(session):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=1_000_00)
    await create_limit(session, user, max_concurrent_contests=1)
    ref = uuid.uuid4()
    await ws.escrow_hold(session, user.id, 5_00, ref_type="match", ref_id=ref)
    with pytest.raises(ls.StakeBlockedError):
        await ls.assert_can_stake(session, user, 1_00)
    await ws.refund(session, user.id, 5_00, ref_type="match", ref_id=ref)
    await ls.assert_can_stake(session, user, 1_00)  # slot freed


def test_promote_pending_respects_cooldown():
    now = datetime.now(UTC)
    limit = Limit(
        user_id=uuid.uuid4(),
        daily_loss_cap_cents=20_000,
        pending_limits={"daily_loss_cap_cents": 40_000},
        pending_effective_at=now + timedelta(hours=1),
    )
    ls.promote_pending(limit, now=now)
    assert limit.daily_loss_cap_cents == 20_000  # not yet effective
    assert limit.pending_limits is not None

    ls.promote_pending(limit, now=now + timedelta(hours=2))
    assert limit.daily_loss_cap_cents == 40_000  # promoted
    assert limit.pending_limits is None
    assert limit.pending_effective_at is None
