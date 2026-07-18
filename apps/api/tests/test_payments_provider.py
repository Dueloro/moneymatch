"""Payments seam (10-phase-7 §1): the demo provider books through the real
ledger, and real rails are guarded in code so a config flip alone is inert."""

from __future__ import annotations

import uuid

import pytest

from moneymatch_api.config import Settings
from moneymatch_api.payments import (
    DemoProvider,
    PaymentProvider,
    PaymentsMisconfiguredError,
    PaymentStatus,
    WebhookError,
    get_payment_provider,
)
from moneymatch_api.services import wallet_service

from .factories import create_user, create_wallet


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://x/y",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s" * 32,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_demo_provider_satisfies_protocol() -> None:
    assert isinstance(DemoProvider(), PaymentProvider)


def test_resolver_returns_demo_when_not_live() -> None:
    provider = get_payment_provider(_settings(payments_live=False))
    assert isinstance(provider, DemoProvider)


def test_resolver_guards_live_flag_in_code() -> None:
    # A config flip alone must never move real money: with no live provider
    # compiled in, `payments_live=true` raises rather than silently degrading.
    with pytest.raises(PaymentsMisconfiguredError):
        get_payment_provider(_settings(payments_live=True))


def test_demo_webhook_unsupported() -> None:
    with pytest.raises(WebhookError):
        DemoProvider().parse_webhook({}, b"{}")


async def test_deposit_intent_books_through_ledger(session) -> None:
    user = await create_user(session)
    await create_wallet(session, user)

    intent = await DemoProvider().create_deposit_intent(session, user.id, 5_000)

    assert intent.status is PaymentStatus.SUCCEEDED
    assert intent.client_action is None
    wallet = await wallet_service.get_wallet(session, user.id)
    assert wallet.available_cents == 5_000
    # The reference is the ledger row id (its idempotency/audit anchor).
    assert uuid.UUID(intent.reference)


async def test_payout_debits_through_ledger(session) -> None:
    user = await create_user(session)
    await create_wallet(session, user)
    await DemoProvider().create_deposit_intent(session, user.id, 5_000)

    result = await DemoProvider().payout(session, user.id, 2_000)

    assert result.status is PaymentStatus.SUCCEEDED
    wallet = await wallet_service.get_wallet(session, user.id)
    assert wallet.available_cents == 3_000
