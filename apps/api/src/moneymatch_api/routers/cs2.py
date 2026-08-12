"""CS2 over Steam: sign in, and submit the share code that settles a wager.

Two surfaces, and they are the whole CS2 loop:

    GET  /cs2/steam/login-url     where to send a user to sign in
    POST /cs2/steam/callback      verify the callback, link the SteamID64
    POST /cs2/sharecode           paste a code, resolve it, store the scoreboard
    POST /cs2/chain               connect automatic collection (one-time setup)
    POST /cs2/chain/sync          pull every match played since the last one
    GET  /cs2/chain               is automatic collection connected and healthy
    GET  /cs2/health              is the Game Coordinator sidecar up

Settlement is not here. A submitted match becomes ordinary match history for
the `cs2.steam` adapter, and the existing pool, tournament and head-to-head
engines grade it exactly as they grade a chess game. That is deliberate: intake
is the only CS2-specific step.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import GAME_CS2_STEAM
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.cs2 import Cs2ShareChain
from ..models.user import User
from ..services import (
    cs2_chain,
    cs2_prior,
    cs2_submission,
    gc_client,
    linking_service,
    steam_openid,
)
from ..services.steam_openid import SteamAuthError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/cs2", tags=["cs2"])


class LoginUrlResponse(BaseModel):
    url: str


class SteamCallbackRequest(BaseModel):
    """Every `openid.*` parameter Steam put on the return URL, unmodified.

    They are forwarded to Steam verbatim for verification, so the client must
    not filter or reorder them.
    """

    params: dict[str, str]


class SteamCallbackResponse(BaseModel):
    steam_id: str
    display_name: str
    linked: bool


class ShareCodeRequest(BaseModel):
    share_code: str = Field(min_length=10, max_length=64)


class ChainConnectRequest(BaseModel):
    #: From Steam's help wizard (appid 730, issue 128). A per-user secret: it
    #: is accepted here, never echoed back, and never logged.
    auth_code: str = Field(min_length=8, max_length=32)
    #: Any share code from a match on this account, as the starting cursor.
    known_code: str = Field(min_length=10, max_length=64)


class ChainStatusResponse(BaseModel):
    connected: bool
    state: str | None = None
    #: Why it stopped, in words the player can act on.
    last_error: str | None = None
    last_polled_at: datetime | None = None
    last_code_at: datetime | None = None


class ChainSyncResponse(BaseModel):
    collected: int
    #: True when the walk stopped on its cap rather than running out of
    #: matches, so the caller knows another sync has more to fetch.
    more_available: bool


class ShareCodePlayer(BaseModel):
    steam_id: str
    kills: int
    deaths: int
    headshots: int
    is_you: bool


class ShareCodeResponse(BaseModel):
    share_code: str
    match_time: datetime
    map_name: str | None
    rounds: int
    score: str
    demo_expired: bool
    your_metrics: dict[str, float]
    players: list[ShareCodePlayer]


class GcHealthResponse(BaseModel):
    ready: bool
    queue_depth: int


@router.get("/steam/login-url", response_model=LoginUrlResponse)
async def steam_login_url() -> LoginUrlResponse:
    """Where to send the user to sign in through Steam."""
    return LoginUrlResponse(url=steam_openid.login_url())


@router.post("/steam/callback", response_model=SteamCallbackResponse)
async def steam_callback(
    body: SteamCallbackRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> SteamCallbackResponse:
    """Verify a Steam sign-in and bind the SteamID64 to the current user."""
    try:
        steam_id = await steam_openid.verify_callback(body.params)
    except SteamAuthError as exc:
        raise APIError("steam_auth_failed", str(exc), status_code=401) from exc

    link = await linking_service.get_link(session, user.id, GAME_CS2_STEAM)
    if link is not None and link.host_account_id != steam_id:
        # A host id that is not a SteamID64 is a placeholder, not a rival
        # claim: seeded demo rows look like `cs2.steam_demo`. Replacing one is
        # the whole point of signing in, so only a genuine second Steam profile
        # is a conflict.
        if link.host_account_id.isdigit():
            raise APIError(
                "steam_already_linked",
                "This account is already linked to a different Steam profile.",
                status_code=409,
            )
        link = await linking_service.rebind(session, user, GAME_CS2_STEAM, steam_id)
    elif link is None:
        link = await linking_service.bind(session, user, GAME_CS2_STEAM, steam_id)

    # A player who has just signed in has no results here, and a pool quotes
    # its bar from your results. Without a prior the answer to "join a wager"
    # is "play a match first", which is a poor thing to say to someone who has
    # just connected an account.
    await cs2_prior.seed(session, user.id, steam_id)
    await session.commit()

    snapshot = link.profile_snapshot or {}
    return SteamCallbackResponse(
        steam_id=steam_id,
        display_name=str(snapshot.get("display_name") or steam_id),
        linked=True,
    )


@router.post("/sharecode", response_model=ShareCodeResponse)
async def submit_share_code(
    body: ShareCodeRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ShareCodeResponse:
    """Resolve a share code, verify it is the user's match, and store it.

    Every rejection carries a reason the player can act on. "Invalid" is not a
    message anyone can do anything with, and the most common cause is a code
    copied from the wrong place.
    """
    link = await linking_service.get_link(session, user.id, GAME_CS2_STEAM)
    if link is None:
        raise APIError(
            "not_linked",
            "Sign in through Steam before submitting a match.",
            status_code=409,
        )
    steam_id = link.host_account_id

    match = await cs2_submission.submit(
        session,
        user_id=user.id,
        steam_id=steam_id,
        share_code=body.share_code,
        # Not scoped to a single contest: the match becomes history, and every
        # in-flight wager whose window contains it grades against it. The
        # per-wager "after you joined" check lives in the window itself.
        joined_at=None,
    )
    await session.commit()

    from ..services.cs2_matches import metrics_from_line

    line = match.line_for(steam_id) or {}
    return ShareCodeResponse(
        share_code=match.share_code,
        match_time=match.match_time,
        map_name=match.map_name,
        rounds=match.rounds_total,
        score=f"{match.score_a}-{match.score_b}",
        demo_expired=match.demo_expired,
        your_metrics={k: round(v, 2) for k, v in metrics_from_line(line).items()},
        players=[
            ShareCodePlayer(
                steam_id=str(p.get("steamid")),
                kills=int(p.get("kills") or 0),
                deaths=int(p.get("deaths") or 0),
                headshots=int(p.get("headshots") or 0),
                is_you=str(p.get("steamid")) == str(steam_id),
            )
            for p in (match.players or [])
        ],
    )


def _chain_status(chain: Cs2ShareChain | None) -> ChainStatusResponse:
    if chain is None:
        return ChainStatusResponse(connected=False)
    return ChainStatusResponse(
        connected=True,
        state=chain.state,
        last_error=chain.last_error,
        last_polled_at=chain.last_polled_at,
        last_code_at=chain.last_code_at,
    )


async def _steam_id_or_409(session: AsyncSession, user: User) -> str:
    link = await linking_service.get_link(session, user.id, GAME_CS2_STEAM)
    if link is None:
        raise APIError(
            "not_linked",
            "Sign in through Steam before setting up automatic collection.",
            status_code=409,
        )
    return str(link.host_account_id)


def _assert_chain_enabled() -> None:
    if not cs2_chain.is_enabled():
        raise APIError(
            "chain_disabled",
            "Automatic match collection is switched off on this server.",
            status_code=404,
        )


@router.post("/chain", response_model=ChainStatusResponse)
async def connect_chain(
    body: ChainConnectRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChainStatusResponse:
    """Connect automatic collection, verifying the credentials before saving.

    Both failures a player can cause are told apart here, because they need
    different fixes: a cursor from someone else's match, and an auth code that
    Steam will not accept.
    """
    _assert_chain_enabled()
    steam_id = await _steam_id_or_409(session, user)
    chain = await cs2_chain.connect(
        session,
        user_id=user.id,
        steam_id=steam_id,
        auth_code=body.auth_code,
        known_code=body.known_code,
    )
    await session.commit()
    return _chain_status(chain)


@router.get("/chain", response_model=ChainStatusResponse)
async def chain_status(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChainStatusResponse:
    """Whether collection is connected. Never returns the auth code."""
    return _chain_status(await cs2_chain.get_chain(session, user.id))


@router.post("/chain/sync", response_model=ChainSyncResponse)
async def sync_chain(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChainSyncResponse:
    """Pull in every match played since the last poll."""
    _assert_chain_enabled()
    matches = await cs2_chain.sync_user(session, user.id)
    await session.commit()
    return ChainSyncResponse(
        collected=len(matches),
        more_available=len(matches) >= cs2_chain.MAX_CODES_PER_SYNC,
    )


@router.get("/health", response_model=GcHealthResponse)
async def gc_health() -> GcHealthResponse:
    """Whether the Game Coordinator sidecar is up, for the status page."""
    health = await gc_client.health()
    return GcHealthResponse(ready=health.ready, queue_depth=health.queue_depth)
