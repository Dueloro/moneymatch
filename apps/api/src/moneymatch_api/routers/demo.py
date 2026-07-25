"""Demo-login bypass — a complete, Supabase-free sign-in for demos.

`POST /demo/login` provisions + onboards a single shared demo user and mints a
short-lived token that `auth.verify_token` accepts **only** when
`demo_login_enabled` is on. It uses its own signing key, so it coexists with real
Supabase auth (Google / email + password keep working). Play-money only — never
enable on a real-money deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthedIdentity
from ..config import Settings, get_settings
from ..constants import (
    DEMO_AUTH_ID,
    DEMO_EMAIL,
    DEMO_JWT_SECRET,
    DEMO_RESIDENCE_STATE,
    DEMO_USERNAME,
    GAME_CS2_FACEIT,
    POOL_METRICS,
    TOURNAMENT_METRICS,
)
from ..db.session import get_session
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.skill import MetricModel
from ..models.user import User
from ..services.user_service import complete_onboarding, get_or_create_user

router = APIRouter(prefix="/demo", tags=["demo"])

_TOKEN_TTL = timedelta(hours=12)

# Plausible baselines (μ, σ) per CS2 metric so the demo user's pool/tournament
# bars and head-to-head duels are all non-provisional out of the box.
_DEMO_METRIC_FIXTURE: dict[str, tuple[float, float]] = {
    "cs2_kd_ratio": (1.15, 0.22),
    "cs2_adr": (78.0, 12.0),
    "cs2_headshot_pct": (47.0, 8.0),
}


async def _ensure_demo_fixture(session: AsyncSession, user: User) -> None:
    """Give the demo user a linked CS2 account + non-provisional metric models so
    the Solo Pools, Tournament, and Head-to-Head pages are populated with joinable
    cards on first login. Idempotent — reuses whatever already exists."""
    link = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id,
            LinkedAccount.game == GAME_CS2_FACEIT,
        )
    )
    if link is None:
        session.add(
            LinkedAccount(
                user_id=user.id,
                game=GAME_CS2_FACEIT,
                host_account_id=f"faceit_{DEMO_USERNAME}",
                host_username=DEMO_USERNAME,
                profile_snapshot={
                    "username": DEMO_USERNAME,
                    "game": GAME_CS2_FACEIT,
                    "total_games": 120,
                    "rank_label": "Level 8",
                    "rating": 1850,
                },
            )
        )

    wanted = set(POOL_METRICS.get(GAME_CS2_FACEIT, ())) | set(
        TOURNAMENT_METRICS.get(GAME_CS2_FACEIT, ())
    )
    have = set(
        await session.scalars(
            select(MetricModel.metric).where(
                MetricModel.user_id == user.id,
                MetricModel.game == GAME_CS2_FACEIT,
            )
        )
    )
    for metric in wanted - have:
        mu, sigma = _DEMO_METRIC_FIXTURE.get(metric, (1.0, 0.2))
        session.add(
            MetricModel(
                user_id=user.id,
                game=GAME_CS2_FACEIT,
                metric=metric,
                mu=mu,
                sigma=sigma,
                n=25,  # non-provisional (>= METRIC_PROVISIONAL_MIN_N)
            )
        )
    await session.flush()


class DemoLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str = DEMO_EMAIL


@router.post("/login", response_model=DemoLoginResponse)
async def demo_login(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> DemoLoginResponse:
    # Belt-and-suspenders: the router is only mounted when enabled, but re-check.
    if not settings.demo_login_enabled:
        raise APIError("not_found", "Not found.", status_code=404)

    # Provision + onboard the shared demo user so the bypass lands straight in
    # (funded DEMO wallet + username set → no onboarding screen).
    user = await get_or_create_user(
        session, AuthedIdentity(auth_id=DEMO_AUTH_ID, email=DEMO_EMAIL)
    )
    if user.username is None:
        await complete_onboarding(
            session,
            user,
            username=DEMO_USERNAME,
            residence_state=DEMO_RESIDENCE_STATE,
            dob_attested_18plus=True,
        )
    # Populate a linked CS2 account + skill models so the pool/tournament/H2H
    # cards render immediately (otherwise the demo lands on "link your account").
    await _ensure_demo_fixture(session, user)
    await session.commit()

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": DEMO_AUTH_ID,
            "email": DEMO_EMAIL,
            "aud": settings.supabase_jwt_audience,
            "demo": True,
            "iat": int(now.timestamp()),
            "exp": int((now + _TOKEN_TTL).timestamp()),
        },
        DEMO_JWT_SECRET,
        algorithm="HS256",
    )
    return DemoLoginResponse(access_token=token)
