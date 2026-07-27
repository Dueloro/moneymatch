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
    POOL_METRICS,
    REGISTERED_GAMES,
    TOURNAMENT_METRICS,
    game_display_name,
)
from ..db.session import get_session
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.skill import MetricModel
from ..models.user import User
from ..services.user_service import complete_onboarding, get_or_create_user

router = APIRouter(prefix="/demo", tags=["demo"])

_TOKEN_TTL = timedelta(hours=12)

# Plausible baselines (μ, σ) per metric so the demo user's pool/tournament bars
# and head-to-head duels are all non-provisional out of the box, on every game.
_DEMO_METRIC_FIXTURE: dict[str, tuple[float, float]] = {
    "chess_accuracy": (85.0, 6.0),
    "cs2_kd_ratio": (1.15, 0.22),
    "cs2_adr": (78.0, 12.0),
    "cs2_headshot_pct": (47.0, 8.0),
    "dota2_kda_ratio": (3.2, 0.8),
    "dota2_gpm": (520.0, 90.0),
    "pubg_kills": (4.5, 2.0),
    "pubg_damage": (380.0, 120.0),
    "pubg_headshot_pct": (22.0, 8.0),
}


async def _ensure_demo_fixture(session: AsyncSession, user: User) -> None:
    """Link the demo user to every playable game + seed non-provisional metric
    models, so Solo Pools, Tournaments, and Head-to-Head are populated with
    joinable cards on every game out of the box. Idempotent."""
    linked = set(
        await session.scalars(
            select(LinkedAccount.game).where(LinkedAccount.user_id == user.id)
        )
    )
    have_models = {
        (g, m)
        for g, m in await session.execute(
            select(MetricModel.game, MetricModel.metric).where(
                MetricModel.user_id == user.id
            )
        )
    }
    for game in REGISTERED_GAMES:
        if game not in linked:
            session.add(
                LinkedAccount(
                    user_id=user.id,
                    game=game,
                    host_account_id=f"{game}_{DEMO_USERNAME}",
                    host_username=DEMO_USERNAME,
                    profile_snapshot={
                        "username": DEMO_USERNAME,
                        "display_name": DEMO_USERNAME,
                        "game": game,
                        "total_games": 120,
                        "win_rate": 0.55,
                        "rank_label": game_display_name(game).split(" — ")[-1],
                    },
                )
            )
        metrics = set(POOL_METRICS.get(game, ())) | set(
            TOURNAMENT_METRICS.get(game, ())
        )
        for metric in metrics:
            if (game, metric) in have_models:
                continue
            mu, sigma = _DEMO_METRIC_FIXTURE.get(metric, (1.0, 0.2))
            session.add(
                MetricModel(
                    user_id=user.id, game=game, metric=metric, mu=mu, sigma=sigma, n=25
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
