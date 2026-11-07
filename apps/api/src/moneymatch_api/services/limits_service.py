"""Server-side staking limits — enforced at escrow time, nowhere else. Daily figures
are trailing-24 h windows read from the immutable ledger, so they cannot be
spoofed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..caps import CAPS
from ..errors import APIError
from ..kyc import KycAction, enforce_kyc
from ..models.user import User
from ..models.wallet import SIGNUP_GRANT_MEMO, LedgerEntry, Limit, Wallet

WINDOW = timedelta(hours=24)
RAISE_COOLDOWN = timedelta(hours=24)


class StakeBlockedError(APIError):
    """A stake was refused by a limit check (RFC-7807 via APIError)."""

    def __init__(self, code: str, message: str, detail: object | None = None) -> None:
        super().__init__(code, message, status_code=422, detail=detail)


@dataclass(frozen=True)
class DailyUsage:
    entry_cents: int
    loss_cents: int
    concurrent: int


async def get_or_create_limits(session: AsyncSession, user_id: uuid.UUID) -> Limit:
    result = await session.execute(select(Limit).where(Limit.user_id == user_id))
    limit = result.scalar_one_or_none()
    if limit is not None:
        return limit
    limit = Limit(user_id=user_id)
    session.add(limit)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(Limit).where(Limit.user_id == user_id))
        limit = result.scalar_one()
    return limit


def promote_pending(limit: Limit, *, now: datetime | None = None) -> Limit:
    """Apply a due cap raise into the live caps (lazy promotion on read)."""
    now = now or datetime.now(UTC)
    if (
        limit.pending_limits
        and limit.pending_effective_at is not None
        and limit.pending_effective_at <= now
    ):
        for field, value in limit.pending_limits.items():
            if hasattr(limit, field):
                setattr(limit, field, value)
        limit.pending_limits = None
        limit.pending_effective_at = None
    return limit


async def request_limit_change(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    daily_loss_cap_cents: int | None = None,
    daily_entry_cap_cents: int | None = None,
    daily_deposit_cap_cents: int | None = None,
    timeout_until: datetime | None = None,
    now: datetime | None = None,
) -> Limit:
    """Apply limit edits: lowering (more protective) is instant; raising a cap is
    staged behind a 24 h cooldown (`pending_limits` + `pending_effective_at`).
    """
    now = now or datetime.now(UTC)
    limit = await get_or_create_limits(session, user_id)
    promote_pending(limit, now=now)

    if timeout_until is not None and (
        limit.timeout_until is None or timeout_until > limit.timeout_until
    ):
        limit.timeout_until = timeout_until

    requested = {
        "daily_loss_cap_cents": daily_loss_cap_cents,
        "daily_entry_cap_cents": daily_entry_cap_cents,
        "daily_deposit_cap_cents": daily_deposit_cap_cents,
    }
    pending = dict(limit.pending_limits or {})
    for field, value in requested.items():
        if value is None:
            continue
        if value <= 0:
            raise APIError("invalid_limit", "Limit must be positive.", status_code=422)
        if value <= getattr(limit, field):
            setattr(limit, field, value)
            pending.pop(field, None)
        else:
            pending[field] = value

    if pending:
        limit.pending_limits = pending
        limit.pending_effective_at = now + RAISE_COOLDOWN
    else:
        limit.pending_limits = None
        limit.pending_effective_at = None

    await session.flush()
    return limit


async def daily_usage(
    session: AsyncSession, wallet: Wallet, *, now: datetime | None = None
) -> DailyUsage:
    now = now or datetime.now(UTC)
    since = now - WINDOW

    entry = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.escrow_delta_cents), 0)).where(
            LedgerEntry.wallet_id == wallet.id,
            LedgerEntry.entry_type == "escrow_hold",
            LedgerEntry.created_at >= since,
        )
    )
    wins = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.wallet_id == wallet.id,
            LedgerEntry.entry_type == "payout",
            LedgerEntry.created_at >= since,
        )
    )
    stakes_lost = await session.scalar(
        select(func.coalesce(func.sum(-LedgerEntry.escrow_delta_cents), 0)).where(
            LedgerEntry.wallet_id == wallet.id,
            LedgerEntry.entry_type == "escrow_release",
            LedgerEntry.created_at >= since,
        )
    )
    net_loss = max(0, int(stakes_lost or 0) - int(wins or 0))

    grouped = (
        select(LedgerEntry.ref_type, LedgerEntry.ref_id)
        .where(LedgerEntry.wallet_id == wallet.id, LedgerEntry.ref_id.isnot(None))
        .group_by(LedgerEntry.ref_type, LedgerEntry.ref_id)
        .having(func.sum(LedgerEntry.escrow_delta_cents) > 0)
        .subquery()
    )
    concurrent = await session.scalar(select(func.count()).select_from(grouped))

    return DailyUsage(
        entry_cents=int(entry or 0),
        loss_cents=net_loss,
        concurrent=int(concurrent or 0),
    )


async def assert_can_deposit(
    session: AsyncSession,
    user: User,
    amount_cents: int,
    *,
    currency: str = "DEMO",
    now: datetime | None = None,
) -> None:
    """Raise `StakeBlockedError` if `amount_cents` would breach the trailing-24 h
    deposit cap — the responsible-gaming guard on funding velocity.
    """
    now = now or datetime.now(UTC)
    if amount_cents <= 0:
        raise StakeBlockedError("invalid_amount", "Amount must be positive.")

    limit = await get_or_create_limits(session, user.id)
    promote_pending(limit, now=now)

    wallet = await session.scalar(
        select(Wallet).where(
            and_(Wallet.user_id == user.id, Wallet.currency == currency)
        )
    )
    deposited = 0
    if wallet is not None:
        deposited = int(
            await session.scalar(
                select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
                    LedgerEntry.wallet_id == wallet.id,
                    LedgerEntry.entry_type == "demo_deposit",
                    LedgerEntry.memo.is_distinct_from(SIGNUP_GRANT_MEMO),
                    LedgerEntry.created_at >= now - WINDOW,
                )
            )
            or 0
        )

    if deposited + amount_cents > limit.daily_deposit_cap_cents:
        raise StakeBlockedError(
            "daily_deposit_cap_exceeded",
            "This would exceed your daily top-up cap.",
            {
                "cap_cents": limit.daily_deposit_cap_cents,
                "used_cents": deposited,
                "requested_cents": amount_cents,
            },
        )


async def assert_can_stake(
    session: AsyncSession,
    user: User,
    amount_cents: int,
    *,
    currency: str = "DEMO",
    now: datetime | None = None,
) -> None:
    """Raise `StakeBlockedError` if `user` may not stake `amount_cents`."""
    if amount_cents <= 0:
        raise StakeBlockedError("invalid_amount", "Stake must be positive.")

    if amount_cents < CAPS.min_entry_cents:
        raise StakeBlockedError(
            "entry_below_min",
            "Stake is below the minimum entry.",
            {"min_entry_cents": CAPS.min_entry_cents, "requested_cents": amount_cents},
        )
    if amount_cents > CAPS.max_entry_cents:
        raise StakeBlockedError(
            "entry_above_max",
            "Stake is above the maximum entry.",
            {"max_entry_cents": CAPS.max_entry_cents, "requested_cents": amount_cents},
        )

    if user.status != "active":
        raise StakeBlockedError(
            "account_not_active",
            f"Account is {user.status}; staking is disabled.",
            {"status": user.status},
        )

    wallet = await session.scalar(
        select(Wallet).where(
            and_(Wallet.user_id == user.id, Wallet.currency == currency)
        )
    )
    if wallet is None:
        raise StakeBlockedError("wallet_not_found", "No wallet for this user.")
    if wallet.available_cents < amount_cents:
        raise StakeBlockedError(
            "insufficient_funds",
            "Not enough points.",
            {
                "available_cents": wallet.available_cents,
                "requested_cents": amount_cents,
            },
        )

    limit = await get_or_create_limits(session, user.id)
    promote_pending(limit, now=now)

    _now = now or datetime.now(UTC)
    if limit.timeout_until is not None and limit.timeout_until > _now:
        raise StakeBlockedError(
            "account_timeout",
            "You're on a self-imposed break. Staking resumes when it ends.",
            {"until": limit.timeout_until.isoformat()},
        )

    usage = await daily_usage(session, wallet, now=now)

    # KYC threshold site (inert at MVP): a stake crossing the cumulative-entry threshold
    # requires verification once kyc_live + a provider are wired.
    enforce_kyc(
        user,
        KycAction.STAKE,
        amount_cents=amount_cents,
        cumulative_entries_cents=usage.entry_cents,
    )

    if usage.entry_cents + amount_cents > limit.daily_entry_cap_cents:
        raise StakeBlockedError(
            "daily_entry_cap_exceeded",
            "This stake would exceed your daily entry cap.",
            {
                "cap_cents": limit.daily_entry_cap_cents,
                "used_cents": usage.entry_cents,
                "requested_cents": amount_cents,
            },
        )
    if usage.loss_cents + amount_cents > limit.daily_loss_cap_cents:
        raise StakeBlockedError(
            "daily_loss_cap_exceeded",
            "This stake would exceed your daily loss cap.",
            {
                "cap_cents": limit.daily_loss_cap_cents,
                "loss_cents": usage.loss_cents,
                "requested_cents": amount_cents,
            },
        )
    if usage.concurrent >= limit.max_concurrent_contests:
        raise StakeBlockedError(
            "concurrent_contests_exceeded",
            "You are in the maximum number of contests at once.",
            {
                "max": limit.max_concurrent_contests,
                "current": usage.concurrent,
            },
        )


async def can_stake(
    session: AsyncSession,
    user: User,
    amount_cents: int,
    *,
    currency: str = "DEMO",
    now: datetime | None = None,
) -> bool:
    """Non-raising `assert_can_stake` — used by room/field formation to decide which
    candidates can be escrowed before committing to a group.
    """
    try:
        await assert_can_stake(session, user, amount_cents, currency=currency, now=now)
        return True
    except StakeBlockedError:
        return False
