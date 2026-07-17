"""`/wallet` — balances, cursor-paginated ledger, and the demo rails.

No endpoint accepts an arbitrary client amount except demo-withdrawal (bounded
by available balance and a daily velocity cap); deposits are server presets.
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.wallet import (
    DEMO_DEPOSIT_PRESETS_CENTS,
    DEMO_WITHDRAWAL_DAILY_LIMIT,
    LedgerEntry,
)
from ..schemas.wallet import (
    DemoDepositRequest,
    DemoWithdrawalRequest,
    LedgerEntryResponse,
    WalletLedgerPage,
    WalletResponse,
)
from ..services import wallet_service

router = APIRouter(prefix="/wallet", tags=["wallet"])

PAGE_SIZE = 20
RECENT_SIZE = 20


def _encode_cursor(entry: LedgerEntry) -> str:
    raw = f"{entry.created_at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), UUID(id_str)
    except (ValueError, binascii.Error) as exc:
        raise APIError(
            "invalid_cursor", "Malformed pagination cursor.", status_code=422
        ) from exc


async def _page(
    session: AsyncSession, wallet_id: UUID, cursor: str | None, size: int
) -> tuple[list[LedgerEntry], str | None]:
    """One descending page of ledger rows, newest first, plus the next cursor."""
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.wallet_id == wallet_id)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(size + 1)  # fetch one extra to detect a further page
    )
    if cursor:
        ts, last_id = _decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(LedgerEntry.created_at, LedgerEntry.id) < (ts, last_id)
        )
    rows = list(await session.scalars(stmt))
    next_cursor = _encode_cursor(rows[size - 1]) if len(rows) > size else None
    return rows[:size], next_cursor


@router.get("", response_model=WalletResponse)
async def get_wallet(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> WalletResponse:
    wallet = await wallet_service.get_wallet(session, user.id)
    recent, _ = await _page(session, wallet.id, cursor=None, size=RECENT_SIZE)
    return WalletResponse(
        currency=wallet.currency,
        available_cents=wallet.available_cents,
        escrow_cents=wallet.escrow_cents,
        lifetime_net_cents=wallet.lifetime_net_cents,
        recent=[LedgerEntryResponse.model_validate(r) for r in recent],
    )


@router.get("/ledger", response_model=WalletLedgerPage)
async def get_ledger(
    user: CurrentUser,
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> WalletLedgerPage:
    wallet = await wallet_service.get_wallet(session, user.id)
    rows, next_cursor = await _page(session, wallet.id, cursor, size=PAGE_SIZE)
    return WalletLedgerPage(
        entries=[LedgerEntryResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post("/demo-deposit", response_model=WalletResponse)
async def demo_deposit(
    body: DemoDepositRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> WalletResponse:
    if body.amount_preset_cents not in DEMO_DEPOSIT_PRESETS_CENTS:
        raise APIError(
            "invalid_deposit_preset",
            "Deposit amount must be one of the offered presets.",
            status_code=422,
            detail={"allowed": list(DEMO_DEPOSIT_PRESETS_CENTS)},
        )
    await wallet_service.demo_deposit(
        session,
        user.id,
        body.amount_preset_cents,
        memo="Add funds",
        created_by=str(user.id),
    )
    return await get_wallet(user, session)


@router.post("/demo-withdrawal", response_model=WalletResponse)
async def demo_withdrawal(
    body: DemoWithdrawalRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> WalletResponse:
    wallet = await wallet_service.get_wallet(session, user.id)
    since = datetime.now(UTC) - timedelta(hours=24)
    if (
        await wallet_service.count_withdrawals_since(session, wallet.id, since)
        >= DEMO_WITHDRAWAL_DAILY_LIMIT
    ):
        raise APIError(
            "withdrawal_velocity_exceeded",
            f"At most {DEMO_WITHDRAWAL_DAILY_LIMIT} withdrawals per day.",
            status_code=429,
        )
    await wallet_service.demo_withdrawal(
        session,
        user.id,
        body.amount_cents,
        memo="Withdrawal",
        created_by=str(user.id),
    )
    return await get_wallet(user, session)
