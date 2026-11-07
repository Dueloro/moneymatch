"""Account linking — the one seam every link flows through."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..constants import REGISTERED_GAMES, game_flag_key
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.user import User
from ..schemas.profile import ProfileSnapshot
from ..services import metric_models_service, raw_payload_service
from ..services.feature_flags import get_boolean_flags
from ..services.hosts.errors import HostError, HostNotConfigured, HostUnavailable

log = structlog.get_logger(__name__)


class LinkError(APIError):
    """Base for link-flow failures (RFC-7807 envelope via APIError)."""


def _unknown_game(game: str) -> LinkError:
    return LinkError(
        "unknown_game",
        f"'{game}' is not a supported game.",
        status_code=404,
        detail={"supported": list(REGISTERED_GAMES)},
    )


async def _assert_game_enabled(session: AsyncSession, game: str) -> None:
    if game not in REGISTERED_GAMES:
        raise _unknown_game(game)
    flags = await get_boolean_flags(session)
    if not flags.get(game_flag_key(game), True):
        raise LinkError(
            "game_disabled",
            "Linking for this game is currently disabled.",
            status_code=409,
        )


async def get_links(session: AsyncSession, user_id: uuid.UUID) -> list[LinkedAccount]:
    """Every live linked account for a user (newest first)."""
    rows = await session.scalars(
        select(LinkedAccount)
        .where(
            LinkedAccount.user_id == user_id,
            LinkedAccount.status != "unbound",
        )
        .order_by(LinkedAccount.created_at.desc())
    )
    return list(rows)


_LINK_RANK = case((LinkedAccount.status == "active", 0), else_=1)


def live_links_for(user_id: uuid.UUID, game: str):
    """The ordered SELECT behind `get_link`, for callers that need the query."""
    return (
        select(LinkedAccount)
        .where(
            LinkedAccount.user_id == user_id,
            LinkedAccount.game == game,
            LinkedAccount.status != "unbound",
        )
        .order_by(_LINK_RANK, LinkedAccount.created_at.desc())
    )


async def get_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount | None:
    """The user's live binding for a game (ignores soft-unbound history rows)."""
    return await session.scalar(live_links_for(user_id, game))


async def _fetch_profile(game: str, method: str, username: str) -> ProfileSnapshot:
    adapter = registry.get(game)
    try:
        return await adapter.link_account(method, username)
    except HostNotConfigured as exc:
        log.error("link.host_not_configured", game=game, error=str(exc))
        raise LinkError(
            "host_not_configured",
            "Linking for this game is temporarily unavailable. Please try again later.",
            status_code=503,
        ) from exc
    except HostUnavailable as exc:
        raise LinkError(
            "host_unavailable",
            "The game's servers are unavailable right now — try again shortly.",
            status_code=502,
        ) from exc
    except HostError as exc:
        # Any other typed host failure (auth 401/403, rate-limit 429, bad request) — a
        # real upstream problem, not a missing player.
        log.warning("link.host_error", game=game, error=str(exc))
        raise LinkError(
            "host_unavailable",
            "The game's servers are unavailable right now — try again shortly.",
            status_code=502,
        ) from exc
    except ValueError as exc:
        raise LinkError("host_account_unlinkable", str(exc), status_code=404) from exc


async def bind(
    session: AsyncSession,
    user: User,
    game: str,
    username: str,
    *,
    method: str = "username",
) -> LinkedAccount:
    """Verify + bind a host account to ``user`` (the single linking seam)."""
    await _assert_game_enabled(session, game)

    profile = await _fetch_profile(game, method, username)
    host_account_id = profile.username.strip().casefold()

    link = LinkedAccount(
        user_id=user.id,
        game=game,
        host_account_id=host_account_id,
        host_username=profile.display_name or username,
        link_method="oauth" if method == "oauth" else "username",
        profile_snapshot=profile.model_dump(),
    )
    session.add(link)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _bind_conflict(exc, game) from exc

    await raw_payload_service.persist(
        session, f"{game}:profile", profile.model_dump(), memo=f"link {username}"
    )
    await metric_models_service.bootstrap(session, user.id, game, host_account_id)

    log.info(
        "link.bound", user_id=str(user.id), game=game, host_account_id=host_account_id
    )
    return link


def _bind_conflict(exc: IntegrityError, game: str) -> LinkError:
    text = str(exc.orig) if exc.orig else str(exc)
    if "uq_linked_accounts_game_host" in text:
        return LinkError(
            "account_already_bound",
            "That game account is already linked to another user.",
            status_code=409,
        )
    if "uq_linked_accounts_user_game" in text:
        return LinkError(
            "already_linked",
            f"You already have a {game} account linked.",
            status_code=409,
        )
    return LinkError("link_conflict", "Could not link that account.", status_code=409)


async def refresh(session: AsyncSession, user: User, game: str) -> LinkedAccount:
    """Re-fetch the snapshot for an already-linked account + refresh its models."""
    link = await get_link(session, user.id, game)
    if link is None:
        raise LinkError("not_linked", f"No {game} account is linked.", status_code=404)
    adapter = registry.get(game)
    try:
        profile = await adapter.fetch_profile(link.host_account_id)
    except HostUnavailable as exc:
        raise LinkError(
            "host_unavailable",
            "The game's servers are unavailable right now — try again shortly.",
            status_code=502,
        ) from exc
    except ValueError as exc:
        raise LinkError("host_account_unlinkable", str(exc), status_code=404) from exc

    link.profile_snapshot = profile.model_dump()
    await session.flush()
    await raw_payload_service.persist(
        session, f"{game}:profile", profile.model_dump(), memo=f"refresh {game}"
    )
    await metric_models_service.bootstrap(session, user.id, game, link.host_account_id)
    return link


async def unlink(session: AsyncSession, user_id: uuid.UUID, game: str) -> None:
    """Remove a binding."""
    link = await get_link(session, user_id, game)
    if link is None:
        raise LinkError("not_linked", f"No {game} account is linked.", status_code=404)
    await session.delete(link)
    await session.flush()
