"""`/challenges` — direct challenges, rematches, and invite links.

Accepting a challenge forms a PENDING match through the shared lifecycle (both
confirm → escrow → activate); the client then navigates to the match slip. The
token preview is **public** (the acquisition funnel's first step — sign-in comes
after). Every write is an intent; the server owns entry cents, expiry, friendly
determination, and match formation (08-phase-5 · deliverable 3).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.social import Challenge
from ..models.user import User
from ..schemas.social import (
    ChallengeAcceptResponse,
    ChallengeCreatedResponse,
    ChallengePreviewResponse,
    ChallengeView,
    CreateChallengeRequest,
)
from ..services import challenge_service
from ..services.markets import get as get_market

router = APIRouter(prefix="/challenges", tags=["challenges"])


async def _view(session: AsyncSession, challenge: Challenge) -> ChallengeView:
    market = get_market(challenge.game, challenge.market)
    challenger = await session.get(User, challenge.challenger_id)
    return ChallengeView(
        id=challenge.id,
        challenger_id=challenge.challenger_id,
        challenger_username=challenger.username if challenger else None,
        challengee_id=challenge.challengee_id,
        game=challenge.game,
        market=challenge.market,
        market_label=market.label if market else challenge.market,
        kind=market.kind if market else "",
        speed=challenge.speed,
        entry_cents=challenge.entry_cents,
        friendly=challenge.friendly,
        state=challenge.state,
        match_id=challenge.match_id,
        is_invite=challenge.invite_token is not None,
        expires_at=challenge.expires_at,
    )


@router.post("", response_model=ChallengeCreatedResponse)
async def create_challenge(
    body: CreateChallengeRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChallengeCreatedResponse:
    if body.rematch_of is not None:
        challenge = await challenge_service.create_rematch(
            session, user, body.rematch_of
        )
    elif body.challengee_id is not None:
        challenge = await _create_direct(session, user, body)
    else:
        challenge = await _create_invite(session, user, body)

    view = await _view(session, challenge)
    if challenge.invite_token is not None:
        return ChallengeCreatedResponse(
            challenge=view,
            invite_token=challenge.invite_token,
            invite_path=f"/i/{challenge.invite_token}",
        )
    return ChallengeCreatedResponse(challenge=view)


def _require_fields(body: CreateChallengeRequest) -> tuple[str, str, int]:
    if not body.game or not body.market or body.entry_preset_cents is None:
        raise APIError(
            "missing_fields",
            "A challenge needs game, market, and an entry preset.",
            status_code=422,
        )
    return body.game, body.market, body.entry_preset_cents


async def _create_direct(
    session: AsyncSession, user: User, body: CreateChallengeRequest
) -> Challenge:
    game, market, entry = _require_fields(body)
    assert body.challengee_id is not None
    return await challenge_service.create_direct(
        session,
        user,
        challengee_id=body.challengee_id,
        game=game,
        market_key=market,
        entry_cents=entry,
        speed=body.speed,
    )


async def _create_invite(
    session: AsyncSession, user: User, body: CreateChallengeRequest
) -> Challenge:
    game, market, entry = _require_fields(body)
    return await challenge_service.create_invite(
        session,
        user,
        game=game,
        market_key=market,
        entry_cents=entry,
        speed=body.speed,
    )


@router.get("/token/{token}", response_model=ChallengePreviewResponse)
async def preview_invite(
    token: str, session: AsyncSession = Depends(get_session)
) -> ChallengePreviewResponse:
    """Public: the invite-link preview shown before sign-in (funnel step 1)."""
    preview = await challenge_service.preview_token(session, token)
    challenge = preview.challenge
    market = get_market(challenge.game, challenge.market)
    return ChallengePreviewResponse(
        game=challenge.game,
        market=challenge.market,
        market_label=market.label if market else challenge.market,
        kind=market.kind if market else "",
        speed=challenge.speed,
        entry_cents=challenge.entry_cents,
        challenger_username=preview.challenger_username,
        state=challenge.state,
        valid=preview.valid,
        expires_at=challenge.expires_at,
    )


@router.post("/token/{token}/accept", response_model=ChallengeAcceptResponse)
async def accept_invite(
    token: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChallengeAcceptResponse:
    match = await challenge_service.accept_invite(session, user, token)
    return ChallengeAcceptResponse(match_id=match.id)


@router.get("/{challenge_id}", response_model=ChallengeView)
async def get_challenge(
    challenge_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChallengeView:
    challenge = await challenge_service.get_for_user(session, user, challenge_id)
    return await _view(session, challenge)


@router.post("/{challenge_id}/accept", response_model=ChallengeAcceptResponse)
async def accept_challenge(
    challenge_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChallengeAcceptResponse:
    match = await challenge_service.accept_direct(session, user, challenge_id)
    return ChallengeAcceptResponse(match_id=match.id)


@router.post("/{challenge_id}/decline", response_model=ChallengeView)
async def decline_challenge(
    challenge_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChallengeView:
    challenge = await challenge_service.decline(session, user, challenge_id)
    return await _view(session, challenge)
