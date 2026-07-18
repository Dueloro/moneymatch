"""KYC seam (10-phase-7 §1): the policy hook is inert at MVP, the flag is
guarded in code, and the threshold logic activates only when kyc_live is on."""

from __future__ import annotations

import uuid

import pytest

from moneymatch_api.caps import CAPS
from moneymatch_api.config import Settings
from moneymatch_api.kyc import (
    DemoKycProvider,
    KycAction,
    KycMisconfiguredError,
    KycProvider,
    KycStatus,
    get_kyc_provider,
    kyc_required,
)
from moneymatch_api.models.user import User


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://x/y",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s" * 32,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _user(kyc_status: str = "none") -> User:
    return User(auth_id="a", username="u", kyc_status=kyc_status)


def test_demo_provider_satisfies_protocol() -> None:
    assert isinstance(DemoKycProvider(), KycProvider)


def test_resolver_returns_demo_when_not_live() -> None:
    assert isinstance(get_kyc_provider(_settings(kyc_live=False)), DemoKycProvider)


def test_resolver_guards_live_flag_in_code() -> None:
    with pytest.raises(KycMisconfiguredError):
        get_kyc_provider(_settings(kyc_live=True))


@pytest.mark.parametrize(
    "action",
    [KycAction.DEPOSIT, KycAction.WITHDRAWAL, KycAction.STAKE],
)
def test_kyc_never_required_at_mvp(action: KycAction) -> None:
    # kyc_live is False → every boundary is inert, even a huge amount.
    assert (
        kyc_required(
            _user(),
            action,
            amount_cents=10_000_000,
            settings=_settings(kyc_live=False),
        )
        is False
    )


def test_verified_user_never_regated_when_live() -> None:
    assert (
        kyc_required(
            _user(kyc_status="verified"),
            KycAction.WITHDRAWAL,
            settings=_settings(kyc_live=True),
        )
        is False
    )


def test_stake_gates_past_threshold_when_live() -> None:
    live = _settings(kyc_live=True)
    below = kyc_required(
        _user(),
        KycAction.STAKE,
        amount_cents=CAPS.kyc_entry_threshold_cents - 1,
        cumulative_entries_cents=0,
        settings=live,
    )
    at = kyc_required(
        _user(),
        KycAction.STAKE,
        amount_cents=1,
        cumulative_entries_cents=CAPS.kyc_entry_threshold_cents - 1,
        settings=live,
    )
    assert below is False
    assert at is True


async def test_demo_provider_auto_verifies() -> None:
    provider = DemoKycProvider()
    v = await provider.start_verification(uuid.uuid4())
    assert v.status is KycStatus.VERIFIED
    assert await provider.get_status(uuid.uuid4()) is KycStatus.VERIFIED
