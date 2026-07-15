"""`/me` — the authenticated user and onboarding."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..models.user import User
from ..schemas.user import MeResponse, OnboardingRequest, UserResponse
from ..services.user_service import complete_onboarding

router = APIRouter(tags=["me"])


def _me(user: User) -> MeResponse:
    return MeResponse(
        user=UserResponse.model_validate(user),
        needs_onboarding=user.username is None,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(user: CurrentUser) -> MeResponse:
    return _me(user)


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: OnboardingRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    user = await complete_onboarding(
        session,
        user,
        username=body.username,
        residence_state=body.residence_state,
        dob_attested_18plus=body.dob_attested_18plus,
    )
    return _me(user)
