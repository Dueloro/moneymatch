"""User provisioning and onboarding.

`get_or_create_user` is the single provisioning path, called from the auth
dependency on every authed request — the row is created (minimally) on first
authed call and reused thereafter (matched by the unique Supabase `auth_id`).
Onboarding (`complete_onboarding`) then sets the immutable username plus the
residence/18+ attestation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthedIdentity
from ..errors import APIError
from ..models.user import User
from ..models.wallet import SIGNUP_GRANT_CENTS, Limit, Wallet
from . import wallet_service


async def get_or_create_user(session: AsyncSession, identity: AuthedIdentity) -> User:
    """Resolve the user row for an identity, creating a minimal one if absent.

    A freshly created user is provisioned with a DEMO wallet, default limits, and
    the signup grant — all in the caller's transaction, so a new account either
    lands fully set up or not at all.
    """
    result = await session.execute(select(User).where(User.auth_id == identity.auth_id))
    user = result.scalar_one_or_none()
    if user is not None:
        # Backfill email if Supabase now has one we didn't record.
        if identity.email and user.email != identity.email:
            user.email = identity.email
        return user

    user = User(auth_id=identity.auth_id, email=identity.email)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # Concurrent first call created it — re-read and use that row.
        await session.rollback()
        result = await session.execute(
            select(User).where(User.auth_id == identity.auth_id)
        )
        return result.scalar_one()

    await provision_new_user(session, user)
    return user


async def provision_new_user(session: AsyncSession, user: User) -> Wallet:
    """Create the DEMO wallet + default limits and post the signup grant.

    The grant is a real `demo_deposit` ledger row funded from `platform:promo`
    (memo "signup grant"), so demo money never appears from nowhere and the
    global solvency invariant holds from the first row (04-phase-1 · deliverable 3).
    """
    wallet = Wallet(user_id=user.id, currency="DEMO")
    session.add(wallet)
    session.add(Limit(user_id=user.id))
    await session.flush()

    await wallet_service.demo_deposit(
        session,
        user.id,
        SIGNUP_GRANT_CENTS,
        memo="signup grant",
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
    """Freeze staking irreversibly (via API). `assert_can_stake` blocks any
    non-active user; escrow already held settles normally through the worker."""
    user.status = "self_excluded"
    await session.flush()
    return user
