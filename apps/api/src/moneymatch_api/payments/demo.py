"""`DemoProvider` — the only `PaymentProvider` implementation at MVP.

Demo money flows through the *same real ledger* as everything else (00-README
§1): a demo deposit is promo-funded, a demo withdrawal returns money to promo.
The rail settles synchronously — there is no external processor and therefore no
webhook — so `create_deposit_intent` books the credit inline and returns a
`SUCCEEDED` intent. This is exactly what Phase 1's demo rails do; the provider
just puts them behind the `PaymentProvider` seam so swapping in real rails is a
provider change, not a router change.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..services import wallet_service
from .base import (
    DepositIntent,
    LedgerEffect,
    PaymentStatus,
    PayoutResult,
    WebhookError,
)

PROVIDER_NAME = "demo"


class DemoProvider:
    """Synchronous, promo-funded demo rails behind the `PaymentProvider` protocol."""

    name = PROVIDER_NAME

    async def create_deposit_intent(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        *,
        memo: str | None = None,
    ) -> DepositIntent:
        entry = await wallet_service.demo_deposit(
            session,
            user_id,
            amount_cents,
            memo=memo or "Add funds",
            created_by=str(user_id),
        )
        return DepositIntent(
            provider=self.name,
            reference=str(entry.id),
            amount_cents=amount_cents,
            status=PaymentStatus.SUCCEEDED,
            client_action=None,  # no redirect: demo settles inline
        )

    async def payout(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        *,
        memo: str | None = None,
    ) -> PayoutResult:
        entry = await wallet_service.demo_withdrawal(
            session,
            user_id,
            amount_cents,
            memo=memo or "Withdrawal",
            created_by=str(user_id),
        )
        return PayoutResult(
            provider=self.name,
            reference=str(entry.id),
            amount_cents=amount_cents,
            status=PaymentStatus.SUCCEEDED,
        )

    def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[LedgerEffect]:
        # The demo rail has no external processor, so it can never receive a
        # webhook. A real provider translates a signed event here.
        raise WebhookError("demo provider has no external webhook")
