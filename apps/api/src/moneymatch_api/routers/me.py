"""`/me` — the authenticated user, onboarding, limits, and self-exclusion."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.user import User
from ..schemas.user import LimitsResponse, MeResponse, UpdateMeRequest, UserResponse
from ..services import limits_service, notifications_service
from ..services.user_service import complete_onboarding, self_exclude

router = APIRouter(tags=["me"])


async def _me(session: AsyncSession, user: User) -> MeResponse:
    limit = await limits_service.get_or_create_limits(session, user.id)
    limits_service.promote_pending(limit)
    unread = await notifications_service.unread_count(session, user.id)
    return MeResponse(
        user=UserResponse.model_validate(user),
        needs_onboarding=user.username is None,
        limits=LimitsResponse.model_validate(limit),
        unread_notifications=unread,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> MeResponse:
    return await _me(session, user)


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: UpdateMeRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    if body.username is not None:
        if body.residence_state is None or body.dob_attested_18plus is None:
            raise APIError(
                "onboarding_incomplete",
                "Onboarding requires username, residence state, and 18+ attestation.",
                status_code=422,
            )
        user = await complete_onboarding(
            session,
            user,
            username=body.username,
            residence_state=body.residence_state,
            dob_attested_18plus=body.dob_attested_18plus,
        )

    if body.daily_loss_cap_cents is not None or body.daily_entry_cap_cents is not None:
        await limits_service.request_limit_change(
            session,
            user.id,
            daily_loss_cap_cents=body.daily_loss_cap_cents,
            daily_entry_cap_cents=body.daily_entry_cap_cents,
        )

    return await _me(session, user)


@router.post("/me/self-exclude", response_model=MeResponse)
async def post_self_exclude(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> MeResponse:
    user = await self_exclude(session, user)
    return await _me(session, user)
