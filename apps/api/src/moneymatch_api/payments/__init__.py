"""Payments seam + the guarded provider resolver."""

from __future__ import annotations

from ..config import Settings, get_settings
from .base import (
    DepositIntent,
    LedgerEffect,
    LedgerEffectKind,
    PaymentProvider,
    PaymentStatus,
    PayoutResult,
    WebhookError,
)
from .demo import DemoProvider

__all__ = [
    "DepositIntent",
    "LedgerEffect",
    "LedgerEffectKind",
    "PaymentProvider",
    "PaymentStatus",
    "PayoutResult",
    "PaymentsMisconfiguredError",
    "WebhookError",
    "get_payment_provider",
]


class PaymentsMisconfiguredError(RuntimeError):
    """Raised when `payments_live=true` but no live provider is available."""


def get_payment_provider(settings: Settings | None = None) -> PaymentProvider:
    """Resolve the active payment provider, guarding real rails in code."""
    settings = settings or get_settings()
    if settings.payments_live:
        raise PaymentsMisconfiguredError(
            "payments_live=true but no live PaymentProvider is compiled in. "
            "Enabling real rails is a code change (register a provider here) "
            "AND a config flip — never the flag alone."
        )
    return DemoProvider()
