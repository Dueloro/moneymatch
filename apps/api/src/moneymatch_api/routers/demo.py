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
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthedIdentity
from ..config import Settings, get_settings
from ..constants import (
    DEMO_AUTH_ID,
    DEMO_EMAIL,
    DEMO_JWT_SECRET,
    DEMO_RESIDENCE_STATE,
    DEMO_USERNAME,
)
from ..db.session import get_session
from ..errors import APIError
from ..services.user_service import complete_onboarding, get_or_create_user

router = APIRouter(prefix="/demo", tags=["demo"])

_TOKEN_TTL = timedelta(hours=12)


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
