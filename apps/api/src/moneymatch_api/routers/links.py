"""`/links` — linked host accounts + the link/refresh/unlink flow.

The server owns verification: POST carries only `{game, username}`; the adapter
fetches and validates the account, and the binding is immutable to users (DELETE
is admin-only in MVP). GET returns a row per registered game so the Profile
screen can render LINKED / BLOCKED / UNLINKED directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import REGISTERED_GAMES, game_display_name, game_flag_key
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..schemas.links import CreateLinkRequest, GameLink, LinksResponse
from ..schemas.profile import ProfileSnapshot
from ..services import linking_service
from ..services.feature_flags import get_boolean_flags

router = APIRouter(prefix="/links", tags=["links"])


def _profile_of(link: LinkedAccount) -> ProfileSnapshot | None:
    try:
        return ProfileSnapshot.model_validate(link.profile_snapshot)
    except ValueError:
        return None


def _game_link(game: str, link: LinkedAccount | None, flag_enabled: bool) -> GameLink:
    blocked = (not flag_enabled) or (link is not None and link.status == "frozen")
    if blocked:
        status = "BLOCKED"
    elif link is not None:
        status = "LINKED"
    else:
        status = "UNLINKED"
    return GameLink(
        game=game,
        display_name=game_display_name(game),
        status=status,
        host_username=link.host_username if link else None,
        linked_at=link.created_at if link else None,
        profile=_profile_of(link) if link else None,
    )


async def _links_response(session: AsyncSession, user_id) -> LinksResponse:
    links = {la.game: la for la in await linking_service.get_links(session, user_id)}
    flags = await get_boolean_flags(session)
    return LinksResponse(
        games=[
            _game_link(game, links.get(game), flags.get(game_flag_key(game), True))
            for game in REGISTERED_GAMES
        ]
    )


@router.get("", response_model=LinksResponse)
async def list_links(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> LinksResponse:
    return await _links_response(session, user.id)


@router.post("", response_model=LinksResponse)
async def create_link(
    body: CreateLinkRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LinksResponse:
    await linking_service.bind(session, user, body.game, body.username)
    return await _links_response(session, user.id)


@router.get("/{game}/profile", response_model=LinksResponse)
async def refresh_link(
    game: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LinksResponse:
    await linking_service.refresh(session, user, game)
    return await _links_response(session, user.id)


@router.delete("/{game}", response_model=LinksResponse)
async def delete_link(
    game: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LinksResponse:
    # Bindings are immutable to users; unlink is an admin action in MVP.
    if user.role != "admin":
        raise APIError(
            "admin_only",
            "Unlinking a game account requires an admin.",
            status_code=403,
        )
    await linking_service.unlink(session, user.id, game)
    return await _links_response(session, user.id)
