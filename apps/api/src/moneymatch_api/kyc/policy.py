"""KYC policy hook + guarded provider resolver."""

from __future__ import annotations

from enum import StrEnum

from ..config import Settings, get_settings
from ..errors import APIError
from ..models.user import User
from .base import KycProvider, KycStatus
from .demo import DemoKycProvider


class KycAction(StrEnum):
    """The money boundaries that ask the policy hook."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    STAKE = "stake"


class KycMisconfiguredError(RuntimeError):
    """Raised when `kyc_live=true` but no live provider is available."""


class KycRequiredError(APIError):
    """Raised at a boundary when the user must complete KYC first."""

    def __init__(self, action: KycAction) -> None:
        super().__init__(
            "kyc_required",
            "Identity verification is required before this action.",
            status_code=403,
            detail={"action": str(action)},
        )


def kyc_required(
    user: User,
    action: KycAction,
    *,
    amount_cents: int | None = None,
    cumulative_entries_cents: int | None = None,
    settings: Settings | None = None,
) -> bool:
    """Does `action` require the user to be KYC-verified first?"""
    settings = settings or get_settings()
    if not settings.kyc_live:
        return False
    if user.kyc_status == KycStatus.VERIFIED:
        return False
    if action is KycAction.WITHDRAWAL:
        return True
    if action in (KycAction.DEPOSIT, KycAction.STAKE):
        from ..caps import CAPS

        projected = (cumulative_entries_cents or 0) + (amount_cents or 0)
        return projected >= CAPS.kyc_entry_threshold_cents
    return False


def enforce_kyc(
    user: User,
    action: KycAction,
    *,
    amount_cents: int | None = None,
    cumulative_entries_cents: int | None = None,
    settings: Settings | None = None,
) -> None:
    """Raise `KycRequiredError` if the policy hook gates `action`."""
    if kyc_required(
        user,
        action,
        amount_cents=amount_cents,
        cumulative_entries_cents=cumulative_entries_cents,
        settings=settings,
    ):
        raise KycRequiredError(action)


def get_kyc_provider(settings: Settings | None = None) -> KycProvider:
    """Resolve the active KYC provider, guarding real verification in code."""
    settings = settings or get_settings()
    if settings.kyc_live:
        raise KycMisconfiguredError(
            "kyc_live=true but no live KycProvider is compiled in. Enabling real "
            "KYC is a code change (register a provider) AND a config flip — "
            "never the flag alone."
        )
    return DemoKycProvider()
