"""`DemoProvider` — the only `PaymentProvider` implementation at MVP. Demo money
flows through the *same real ledger* as everything else: a demo deposit is promo-
funded, a demo withdrawal returns money to promo.
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
            memo=memo or "Points added",
            created_by=str(user_id),
        )
        return DepositIntent(
            provider=self.name,
            reference=str(entry.id),
            amount_cents=amount_cents,
            status=PaymentStatus.SUCCEEDED,
            client_action=None,
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
            memo=memo or "Points removed",
            created_by=str(user_id),
        )
        return PayoutResult(
            provider=self.name,
            reference=str(entry.id),
            amount_cents=amount_cents,
            status=PaymentStatus.SUCCEEDED,
        )

    def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[LedgerEffect]:
        raise WebhookError("demo provider has no external webhook")
