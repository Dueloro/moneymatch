"""Phase-1 caps table (10-phase-7 §1): the values match overview.md §7.3 and
the entry band enforces server-side at the staking boundary."""

from __future__ import annotations

import pytest

from moneymatch_api.caps import CAPS
from moneymatch_api.models.wallet import (
    DEFAULT_DAILY_ENTRY_CAP_CENTS,
    DEFAULT_DAILY_LOSS_CAP_CENTS,
    DEFAULT_MAX_CONCURRENT_CONTESTS,
)
from moneymatch_api.services.limits_service import StakeBlockedError, assert_can_stake

from .factories import create_user, create_wallet


def test_caps_match_overview_7_3() -> None:
    assert CAPS.min_entry_cents == 100  # $1
    assert CAPS.max_entry_cents == 10_000  # $100
    assert CAPS.daily_loss_cap_cents == 20_000  # $200
    assert CAPS.daily_entry_cap_cents == 50_000  # $500
    assert CAPS.kyc_entry_threshold_cents == 50_000  # $500 cumulative
    assert CAPS.withdrawal_min_cents == 2_000  # $20
    assert CAPS.max_concurrent_contests == 3


def test_limit_defaults_sourced_from_caps() -> None:
    # The `limits` server-defaults and the caps table can never drift.
    assert DEFAULT_DAILY_LOSS_CAP_CENTS == CAPS.daily_loss_cap_cents
    assert DEFAULT_DAILY_ENTRY_CAP_CENTS == CAPS.daily_entry_cap_cents
    assert DEFAULT_MAX_CONCURRENT_CONTESTS == CAPS.max_concurrent_contests


async def test_entry_below_min_blocked(session) -> None:
    user = await create_user(session)
    await create_wallet(session, user, available_cents=100_000)
    with pytest.raises(StakeBlockedError) as exc:
        await assert_can_stake(session, user, CAPS.min_entry_cents - 1)
    assert exc.value.code == "entry_below_min"


async def test_entry_above_max_blocked(session) -> None:
    user = await create_user(session)
    await create_wallet(session, user, available_cents=1_000_000)
    with pytest.raises(StakeBlockedError) as exc:
        await assert_can_stake(session, user, CAPS.max_entry_cents + 1)
    assert exc.value.code == "entry_above_max"
