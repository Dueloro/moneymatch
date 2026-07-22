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
from ..models.user import User, gen_friend_code
from ..models.wallet import SIGNUP_GRANT_CENTS, Limit, Wallet
from . import wallet_service

# A friend_code collision is one-in-a-billion, but a clean signup must never 500
# on the unique constraint; regenerate and retry a few times (backlog · Phase 5).
_FRIEND_CODE_ATTEMPTS = 5


async def get_or_create_user(session: AsyncSession, identity: AuthedIdentity) -> User:
    """Resolve the user row for an identity, creating a minimal one if absent.

    A freshly created user is provisioned with a DEMO wallet, default limits, and
    the signup grant — all in the caller's transaction, so a new account either
    lands fully set up or not at all.

    A unique-constraint conflict on insert is disambiguated by re-reading the
    `auth_id`: if the row now exists a concurrent first call created it (use that
    row); otherwise the collision was on the random `friend_code`, so we retry
    with a fresh one rather than 500 a clean signup. This is schema-name-agnostic
    (no constraint-name string matching) and safe for the caller's transaction.
    """
    result = await session.execute(select(User).where(User.auth_id == identity.auth_id))
    user = result.scalar_one_or_none()
    if user is not None:
        # Backfill email if Supabase now has one we didn't record.
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
            continue  # friend_code collision — retry with a fresh code
        await provision_new_user(session, user)
        return user

    assert last_exc is not None  # loop only exits early via return
    raise last_exc


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
