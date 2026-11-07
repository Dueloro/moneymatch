"""The single module that mutates money: wallet row locked (`FOR UPDATE`), balances
and the append-only `ledger_entries` row written in one transaction. Callers own
the commit; these functions only flush.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import APIError
from ..models.wallet import LedgerEntry, PlatformLedgerEntry, Wallet

DEMO = "DEMO"
SYSTEM = "system"


class WalletError(APIError):
    """Base for money-mutation failures (RFC-7807 envelope via APIError)."""


class InsufficientFundsError(WalletError):
    def __init__(self, available_cents: int, requested_cents: int) -> None:
        super().__init__(
            "insufficient_funds",
            "Not enough available balance for this operation.",
            status_code=422,
            detail={
                "available_cents": available_cents,
                "requested_cents": requested_cents,
            },
        )


class WalletNotFoundError(WalletError):
    def __init__(self) -> None:
        super().__init__(
            "wallet_not_found",
            "No wallet exists for this user and currency.",
            status_code=404,
        )


def _require_positive(amount_cents: int) -> None:
    if amount_cents <= 0:
        raise WalletError(
            "invalid_amount",
            "Amount must be a positive number of cents.",
            status_code=422,
            detail={"amount_cents": amount_cents},
        )


async def get_wallet(
    session: AsyncSession, user_id: uuid.UUID, *, currency: str = DEMO
) -> Wallet:
    """Fetch the wallet for reads (no lock)."""
    wallet = await get_wallet_or_none(session, user_id, currency=currency)
    if wallet is None:
        raise WalletNotFoundError()
    return wallet


async def get_wallet_or_none(
    session: AsyncSession, user_id: uuid.UUID, *, currency: str = DEMO
) -> Wallet | None:
    """Fetch the wallet for reads, or None (admin views over any user)."""
    return await session.scalar(
        select(Wallet).where(Wallet.user_id == user_id, Wallet.currency == currency)
    )


async def lock_wallet(
    session: AsyncSession, user_id: uuid.UUID, *, currency: str = DEMO
) -> Wallet:
    """Fetch the wallet `FOR UPDATE`, serializing concurrent mutations on it."""
    result = await session.execute(
        select(Wallet)
        .where(Wallet.user_id == user_id, Wallet.currency == currency)
        .with_for_update()
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise WalletNotFoundError()
    return wallet


async def count_withdrawals_since(
    session: AsyncSession, wallet_id: uuid.UUID, since
) -> int:
    """Number of demo withdrawals on a wallet since `since` (velocity cap)."""
    count = await session.scalar(
        select(func.count())
        .select_from(LedgerEntry)
        .where(
            LedgerEntry.wallet_id == wallet_id,
            LedgerEntry.entry_type == "demo_withdrawal",
            LedgerEntry.created_at >= since,
        )
    )
    return int(count or 0)


async def _apply(
    session: AsyncSession,
    wallet: Wallet,
    *,
    entry_type: str,
    available_delta: int,
    escrow_delta: int,
    lifetime_delta: int,
    ref_type: str,
    ref_id: uuid.UUID | None,
    memo: str | None,
    created_by: str | None,
) -> LedgerEntry:
    """Apply signed deltas to a locked wallet and append its ledger row."""
    new_available = wallet.available_cents + available_delta
    new_escrow = wallet.escrow_cents + escrow_delta
    if new_available < 0:
        raise InsufficientFundsError(wallet.available_cents, -available_delta)
    if new_escrow < 0:
        raise WalletError(
            "escrow_underflow",
            "Escrow cannot go negative.",
            status_code=422,
            detail={"escrow_cents": wallet.escrow_cents, "delta": escrow_delta},
        )

    wallet.available_cents = new_available
    wallet.escrow_cents = new_escrow
    wallet.lifetime_net_cents += lifetime_delta

    entry = LedgerEntry(
        wallet_id=wallet.id,
        entry_type=entry_type,
        amount_cents=available_delta,
        escrow_delta_cents=escrow_delta,
        ref_type=ref_type,
        ref_id=ref_id,
        balance_after_cents=new_available,
        memo=memo,
        created_by=created_by,
    )
    session.add(entry)
    await session.flush()
    return entry


async def _book_platform(
    session: AsyncSession,
    account: str,
    amount_cents: int,
    *,
    ref_type: str,
    ref_id: uuid.UUID | None,
    memo: str | None,
    created_by: str | None,
) -> PlatformLedgerEntry:
    """Append a platform row; an advisory lock keeps `balance_after_cents` monotonic."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:account))"),
        {"account": account},
    )
    current = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.account == account
        )
    )
    balance_after = int(current or 0) + amount_cents
    row = PlatformLedgerEntry(
        account=account,
        amount_cents=amount_cents,
        balance_after_cents=balance_after,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def demo_deposit(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    memo: str | None = None,
    created_by: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> LedgerEntry:
    """Credit available balance, funded from `platform:promo`."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    entry = await _apply(
        session,
        wallet,
        entry_type="demo_deposit",
        available_delta=amount_cents,
        escrow_delta=0,
        lifetime_delta=0,
        ref_type="demo_rail",
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or SYSTEM,
    )
    await _book_platform(
        session,
        "platform:promo",
        -amount_cents,
        ref_type="demo_rail",
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or SYSTEM,
    )
    return entry


async def demo_withdrawal(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    memo: str | None = None,
    created_by: str | None = None,
) -> LedgerEntry:
    """Debit available balance; money leaves the economy back to `platform:promo`."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    entry = await _apply(
        session,
        wallet,
        entry_type="demo_withdrawal",
        available_delta=-amount_cents,
        escrow_delta=0,
        lifetime_delta=0,
        ref_type="demo_rail",
        ref_id=None,
        memo=memo,
        created_by=created_by or str(user_id),
    )
    await _book_platform(
        session,
        "platform:promo",
        amount_cents,
        ref_type="demo_rail",
        ref_id=None,
        memo=memo,
        created_by=created_by or str(user_id),
    )
    return entry


async def escrow_hold(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    ref_type: str,
    ref_id: uuid.UUID,
    memo: str | None = None,
    created_by: str | None = None,
) -> LedgerEntry:
    """Move `amount` from available → escrow when joining a contest."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    return await _apply(
        session,
        wallet,
        entry_type="escrow_hold",
        available_delta=-amount_cents,
        escrow_delta=amount_cents,
        lifetime_delta=0,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or str(user_id),
    )


async def escrow_release(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    ref_type: str,
    ref_id: uuid.UUID,
    memo: str | None = None,
    created_by: str | None = None,
) -> LedgerEntry:
    """Consume an escrowed stake at settlement (the stake funds the pot). The
    matching gains are a `payout` (to the winner) and `rake` (to the platform).
    """
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    return await _apply(
        session,
        wallet,
        entry_type="escrow_release",
        available_delta=0,
        escrow_delta=-amount_cents,
        lifetime_delta=-amount_cents,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or SYSTEM,
    )


async def payout(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    ref_type: str,
    ref_id: uuid.UUID,
    memo: str | None = None,
    created_by: str | None = None,
) -> LedgerEntry:
    """Credit a prize to available; records the win in lifetime P&L."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    return await _apply(
        session,
        wallet,
        entry_type="payout",
        available_delta=amount_cents,
        escrow_delta=0,
        lifetime_delta=amount_cents,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or SYSTEM,
    )


async def refund(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    ref_type: str,
    ref_id: uuid.UUID,
    memo: str | None = None,
    created_by: str | None = None,
) -> LedgerEntry:
    """Return an escrowed stake to available on a push/cancel — zero rake, no P&L."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    return await _apply(
        session,
        wallet,
        entry_type="refund",
        available_delta=amount_cents,
        escrow_delta=-amount_cents,
        lifetime_delta=0,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or SYSTEM,
    )


async def rake(
    session: AsyncSession,
    amount_cents: int,
    *,
    ref_type: str,
    ref_id: uuid.UUID,
    memo: str | None = None,
    created_by: str | None = None,
) -> PlatformLedgerEntry | None:
    """Book rake to `platform:rake`."""
    if amount_cents == 0:
        return None
    _require_positive(amount_cents)
    return await _book_platform(
        session,
        "platform:rake",
        amount_cents,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
        created_by=created_by or SYSTEM,
    )


async def credit(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    memo: str,
    created_by: str,
    ref_id: uuid.UUID | None = None,
) -> LedgerEntry:
    """Admin correction crediting available, funded from `platform:promo`."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    entry = await _apply(
        session,
        wallet,
        entry_type="adjustment",
        available_delta=amount_cents,
        escrow_delta=0,
        lifetime_delta=0,
        ref_type="admin",
        ref_id=ref_id,
        memo=memo,
        created_by=created_by,
    )
    await _book_platform(
        session,
        "platform:promo",
        -amount_cents,
        ref_type="admin",
        ref_id=ref_id,
        memo=memo,
        created_by=created_by,
    )
    return entry


async def debit(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount_cents: int,
    *,
    memo: str,
    created_by: str,
    ref_id: uuid.UUID | None = None,
) -> LedgerEntry:
    """Admin correction debiting available, returned to `platform:promo`."""
    _require_positive(amount_cents)
    wallet = await lock_wallet(session, user_id)
    entry = await _apply(
        session,
        wallet,
        entry_type="adjustment",
        available_delta=-amount_cents,
        escrow_delta=0,
        lifetime_delta=0,
        ref_type="admin",
        ref_id=ref_id,
        memo=memo,
        created_by=created_by,
    )
    await _book_platform(
        session,
        "platform:promo",
        amount_cents,
        ref_type="admin",
        ref_id=ref_id,
        memo=memo,
        created_by=created_by,
    )
    return entry
