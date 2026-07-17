"""Wallet / ledger request + response schemas (cents on the wire)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models.wallet import DEMO_DEPOSIT_PRESETS_CENTS


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entry_type: str
    amount_cents: int
    escrow_delta_cents: int
    ref_type: str
    ref_id: UUID | None
    balance_after_cents: int
    memo: str | None
    created_at: datetime


class WalletResponse(BaseModel):
    """Balances + the most recent ledger rows (the Wallet screen's first paint)."""

    currency: str
    available_cents: int
    escrow_cents: int
    lifetime_net_cents: int
    recent: list[LedgerEntryResponse]


class WalletLedgerPage(BaseModel):
    """Cursor-paginated ledger. `next_cursor` is null on the last page."""

    entries: list[LedgerEntryResponse]
    next_cursor: str | None


class DemoDepositRequest(BaseModel):
    """Server-defined preset only — never an arbitrary client amount."""

    amount_preset_cents: int = Field(
        ...,
        description=f"One of the presets: {list(DEMO_DEPOSIT_PRESETS_CENTS)}",
    )


class DemoWithdrawalRequest(BaseModel):
    amount_cents: int = Field(..., gt=0, description="Cents; must be ≤ available")
