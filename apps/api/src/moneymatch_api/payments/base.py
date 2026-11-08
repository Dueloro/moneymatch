"""The `PaymentProvider` seam."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


class PaymentStatus(StrEnum):
    """Lifecycle of a deposit intent or payout."""

    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"


class LedgerEffectKind(StrEnum):
    """The wallet mutation a settled provider event asks the caller to book."""

    CREDIT_AVAILABLE = "credit_available"
    DEBIT_AVAILABLE = "debit_available"


@dataclass(frozen=True)
class DepositIntent:
    """The provider's answer to "the user wants to add `amount_cents`." `status is
    SUCCEEDED` means the funds are already booked (demo rails, which settle
    inline).
    """

    provider: str
    reference: str
    amount_cents: int
    status: PaymentStatus
    client_action: str | None = None


@dataclass(frozen=True)
class PayoutResult:
    """The provider's answer to a withdrawal request."""

    provider: str
    reference: str
    amount_cents: int
    status: PaymentStatus


@dataclass(frozen=True)
class LedgerEffect:
    """A settled money movement a webhook asks the caller to book. The caller applies
    these through `wallet_service` so the ledger stays the single source of truth;
    the provider never touches wallet rows itself.
    """

    user_id: uuid.UUID
    kind: LedgerEffectKind
    amount_cents: int
    reference: str
    memo: str


class WebhookError(Exception):
    """Raised when an inbound webhook fails signature/parse validation."""


@runtime_checkable
class PaymentProvider(Protocol):
    """The contract every deposit/withdrawal rail implements."""

    name: str

    async def create_deposit_intent(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        *,
        memo: str | None = None,
    ) -> DepositIntent: ...

    async def payout(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        *,
        memo: str | None = None,
    ) -> PayoutResult: ...

    def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[LedgerEffect]:
        """Verify + translate a processor webhook into ledger effects."""
        ...
