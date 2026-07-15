"""Direct-insert factories for service/DB tests.

These bypass the HTTP layer and (deliberately) the wallet_service so a test can
arrange a known starting balance before exercising the money primitives. Real
provisioning + signup grant is tested separately.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from moneymatch_api.models.user import User
from moneymatch_api.models.wallet import Limit, Wallet


async def create_user(
    session: AsyncSession,
    *,
    username: str | None = None,
    residence_state: str = "MA",
    status: str = "active",
) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        auth_id=f"auth_{suffix}",
        username=username or f"u_{suffix}",
        email=f"{suffix}@example.com",
        residence_state=residence_state,
        dob_attested_18plus=True,
        status=status,
    )
    session.add(user)
    await session.flush()
    return user


async def create_wallet(
    session: AsyncSession,
    user: User,
    *,
    available_cents: int = 0,
    escrow_cents: int = 0,
    currency: str = "DEMO",
) -> Wallet:
    wallet = Wallet(
        user_id=user.id,
        currency=currency,
        available_cents=available_cents,
        escrow_cents=escrow_cents,
        lifetime_net_cents=0,
    )
    session.add(wallet)
    await session.flush()
    return wallet


async def create_limit(session: AsyncSession, user: User, **overrides) -> Limit:
    limit = Limit(user_id=user.id, **overrides)
    session.add(limit)
    await session.flush()
    return limit
