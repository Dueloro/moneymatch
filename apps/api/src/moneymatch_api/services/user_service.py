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


async def get_or_create_user(session: AsyncSession, identity: AuthedIdentity) -> User:
    """Resolve the user row for an identity, creating a minimal one if absent."""
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
        user = result.scalar_one()
    return user


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
