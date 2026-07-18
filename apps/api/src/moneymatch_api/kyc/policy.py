"""KYC policy hook + guarded provider resolver (10-phase-7 §1).

`kyc_required` is the single decision point asked at every money boundary
(deposit, withdrawal, stake). At MVP it returns False for everyone because
`kyc_live` is False — but the call sites exist and are tested, so real KYC is an
additive integration: register a provider, flip `kyc_live`, and this starts
gating past the configured cumulative-entry threshold (caps.py).

`get_kyc_provider` guards the flag in code: `kyc_live=true` with no live provider
compiled in raises, so a config flip alone can never begin gating on real KYC.
"""

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
    """Does `action` require the user to be KYC-verified first?

    Always False at MVP (`kyc_live` is False). When a real integration flips the
    flag: an already-verified user is never re-gated; a withdrawal or a stake
    that crosses the cumulative-entry threshold requires verification.
    """
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
            "never the flag alone (10-phase-7 §1)."
        )
    return DemoKycProvider()
