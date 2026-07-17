"""Direct-insert factories for service/DB tests.

These bypass the HTTP layer and (deliberately) the wallet_service so a test can
arrange a known starting balance before exercising the money primitives. Real
provisioning + signup grant is tested separately.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.skill import MetricModel
from moneymatch_api.models.user import User
from moneymatch_api.models.wallet import Limit, Wallet
from moneymatch_api.schemas.profile import FormatStat, ProfileSnapshot


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


def chess_profile(
    username: str, *, rating: int = 1500, speed: str = "blitz", total_games: int = 100
) -> ProfileSnapshot:
    return ProfileSnapshot(
        username=username,
        display_name=username,
        url=f"https://lichess.org/@/{username}",
        link_method="username",
        game="chess.lichess",
        win_rate=0.5,
        total_games=total_games,
        formats=[FormatStat(speed=speed, rating=rating, games=total_games)],
        primary_speed=speed,
    )


def cs2_profile(
    username: str, *, rating: int = 1500, total_games: int = 60
) -> ProfileSnapshot:
    return ProfileSnapshot(
        username=username,
        display_name=username,
        url=f"https://faceit.com/players/{username}",
        link_method="username",
        game="cs2.faceit",
        win_rate=0.5,
        total_games=total_games,
        rating=rating,
    )


async def create_linked_account(
    session: AsyncSession,
    user: User,
    game: str,
    *,
    host_account_id: str | None = None,
    profile: ProfileSnapshot | None = None,
) -> LinkedAccount:
    host = host_account_id or f"host_{uuid.uuid4().hex[:10]}"
    link = LinkedAccount(
        user_id=user.id,
        game=game,
        host_account_id=host,
        host_username=host,
        profile_snapshot=profile.model_dump() if profile else {},
    )
    session.add(link)
    await session.flush()
    return link


async def create_metric_model(
    session: AsyncSession,
    user: User,
    game: str,
    metric: str,
    *,
    mu: float,
    sigma: float,
    n: int,
) -> MetricModel:
    model = MetricModel(
        user_id=user.id, game=game, metric=metric, mu=mu, sigma=sigma, n=n
    )
    session.add(model)
    await session.flush()
    return model
