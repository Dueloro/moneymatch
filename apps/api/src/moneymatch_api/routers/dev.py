"""Dev/e2e-only routes — the browser test-auth seam (backlog · Phase 3/7).

`POST /dev/e2e/token` mints a short-lived HS256 JWT for a given `auth_id`, so the
Playwright suite can sign in as seeded users (`seed_player1`, …) headless without
a live Supabase project. The token is verified by the same `auth.verify_token`
path as a real Supabase JWT — nothing about the auth boundary is weakened; this
router is simply **never mounted in prod** (`create_app` gates it on
`e2e_auth_enabled AND env != 'prod'`), and the handler re-checks both.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..errors import APIError

router = APIRouter(prefix="/dev", tags=["dev"])

_TOKEN_TTL = timedelta(hours=1)


class E2ETokenRequest(BaseModel):
    auth_id: str
    email: str | None = None


class E2ETokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_id: str
    email: str | None = None


@router.post("/e2e/token", response_model=E2ETokenResponse)
async def mint_e2e_token(
    body: E2ETokenRequest,
    settings: Settings = Depends(get_settings),
) -> E2ETokenResponse:
    # Belt-and-suspenders: the router is only mounted when enabled + non-prod, but
    # re-check here so a stray mount can never mint tokens in production.
    if settings.env == "prod" or not settings.e2e_auth_enabled:
        raise APIError("not_found", "Not found.", status_code=404)
    if not settings.supabase_jwt_secret:
        raise APIError(
            "e2e_auth_unavailable",
            "An HS256 SUPABASE_JWT_SECRET is required to mint e2e tokens.",
            status_code=409,
        )

    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": body.auth_id,
        "aud": settings.supabase_jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + _TOKEN_TTL).timestamp()),
    }
    if body.email:
        claims["email"] = body.email
    token = jwt.encode(claims, settings.supabase_jwt_secret, algorithm="HS256")
    return E2ETokenResponse(access_token=token, auth_id=body.auth_id, email=body.email)
