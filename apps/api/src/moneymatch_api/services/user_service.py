"""User provisioning and onboarding."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthedIdentity
from ..errors import APIError
from ..models.user import User, gen_friend_code
from ..models.wallet import SIGNUP_GRANT_CENTS, SIGNUP_GRANT_MEMO, Limit, Wallet
from . import wallet_service

_FRIEND_CODE_ATTEMPTS = 5


async def get_or_create_user(session: AsyncSession, identity: AuthedIdentity) -> User:
    """Resolve the user row for an identity, creating a minimal one if absent."""
    result = await session.execute(select(User).where(User.auth_id == identity.auth_id))
    user = result.scalar_one_or_none()
    if user is not None:
        if identity.email and user.email != identity.email:
            user.email = identity.email
        return user

    last_exc: IntegrityError | None = None
    for _ in range(_FRIEND_CODE_ATTEMPTS):
        user = User(
            auth_id=identity.auth_id,
            email=identity.email,
            friend_code=gen_friend_code(),
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            last_exc = exc
            existing = await session.scalar(
                select(User).where(User.auth_id == identity.auth_id)
            )
            if existing is not None:
                return existing  # concurrent create won the auth_id race
            continue
        await provision_new_user(session, user)
        return user

    assert last_exc is not None
    raise last_exc


async def provision_new_user(session: AsyncSession, user: User) -> Wallet:
    """The grant is a real `demo_deposit` ledger row funded from `platform:promo`
    (memo "signup grant"), so demo money never appears from nowhere and the global
    solvency invariant holds from the first row.
    """
    wallet = Wallet(user_id=user.id, currency="DEMO")
    session.add(wallet)
    session.add(Limit(user_id=user.id))
    await session.flush()

    await wallet_service.demo_deposit(
        session,
        user.id,
        SIGNUP_GRANT_CENTS,
        memo=SIGNUP_GRANT_MEMO,
        created_by=wallet_service.SYSTEM,
    )
    return wallet


async def complete_onboarding(
    session: AsyncSession,
    user: User,
    *,
    username: str,
    residence_state: str,
    dob_attested_18plus: bool,
) -> User:
    """Set the immutable username + residence/18+ attestation (onboarding step 2)."""
    if user.username is not None:
        raise APIError(
            "username_immutable",
            "Username is already set and cannot be changed.",
            status_code=409,
        )
    if not dob_attested_18plus:
        raise APIError(
            "attestation_required",
            "You must attest that you are 18 or older.",
            status_code=422,
        )

    user.username = username
    user.residence_state = residence_state.upper()
    user.dob_attested_18plus = True

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise APIError(
            "username_taken",
            "That username is already taken.",
            status_code=409,
        ) from exc
    return user


async def self_exclude(session: AsyncSession, user: User) -> User:
    """Freeze staking irreversibly (via API)."""
    user.status = "self_excluded"
    await session.flush()
    return user
