"""The `PaymentProvider` seam (10-phase-7 §1).

Real payment rails are a Stage-C workstream gated on counsel + underwriting
(`docs/legal/legal-compliance.md` §4–5). The MVP ships the *interface* so that
integration is purely additive: a future Aeropay/Nuvei/Stripe provider
implements this same protocol, and the only code that changes is the provider
module — call sites (the wallet router) already speak `PaymentProvider`.

Design mirrors the engineering invariant that *the server owns every number*
(00-README §3.1): the client sends an intent (a preset id / a bounded amount),
the provider decides the money movement, and every settled effect is a
`LedgerEffect` the caller books through `wallet_service` in one transaction.

A real provider's deposits settle asynchronously: `create_deposit_intent`
returns a `PENDING` intent with a `client_action` (redirect / client secret),
and the credit lands later when the processor's signed webhook is translated by
`parse_webhook` into `LedgerEffect`s. The demo provider settles synchronously
and has no webhook — see `demo.py`.
"""

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

    CREDIT_AVAILABLE = "credit_available"  # a deposit settled
    DEBIT_AVAILABLE = "debit_available"  # a payout / withdrawal settled


@dataclass(frozen=True)
class DepositIntent:
    """The provider's answer to "the user wants to add `amount_cents`."

    `status is SUCCEEDED` means the funds are already booked (demo rails, which
    settle inline). A real provider returns `PENDING` with a `client_action` the
    web app hands to the processor SDK; the credit lands on the webhook.
    """

    provider: str
    reference: str  # provider-side id; also the ledger idempotency key
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
    """A settled money movement a webhook asks the caller to book.

    The caller applies these through `wallet_service` so the ledger stays the
    single source of truth; the provider never touches wallet rows itself.
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
        """Verify + translate a processor webhook into ledger effects.

        Pure translation: the caller books the returned effects. A provider with
        no external webhook (the demo rails) raises `WebhookError`.
        """
        ...
