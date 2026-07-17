"""Account linking — the one seam every link flows through (05-phase-2).

`bind` verifies a host account via its adapter, persists the evidence, creates
the immutable binding (DB-enforced uniqueness), and bootstraps the metric models
— all in the caller's transaction. Username-claim linking ships at MVP; OAuth
drops in later behind the same `bind(user, game, evidence)` seam (the
`link_method` arg + column reserve it).
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
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
from ..services.hosts.errors import HostUnavailable

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
    """Every linked account for a user (newest first)."""
    rows = await session.scalars(
        select(LinkedAccount)
        .where(LinkedAccount.user_id == user_id)
        .order_by(LinkedAccount.created_at.desc())
    )
    return list(rows)


async def get_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount | None:
    return await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user_id, LinkedAccount.game == game
        )
    )


async def _fetch_profile(game: str, method: str, username: str) -> ProfileSnapshot:
    """Resolve + verify a host account through its adapter, mapping host failures
    to clean API errors (bad username → 404, host outage → 502)."""
    adapter = registry.get(game)
    try:
        return await adapter.link_account(method, username)
    except HostUnavailable as exc:
        raise LinkError(
            "host_unavailable",
            "The game's servers are unavailable right now — try again shortly.",
            status_code=502,
        ) from exc
    except ValueError as exc:
        # Unknown username, private/CS:GO-only account, or Dota expose-data off.
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
    # Casefold the host id so the (game, host_account_id) uniqueness catches
    # case-variant claims of the same account; keep the display handle as typed.
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

    # Retain the linking evidence and bootstrap the skill models in the same
    # transaction, so a link either lands fully set up or not at all.
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
    """Remove a binding. Admin-only in MVP (bindings are immutable to users);
    unlinking while a contest is in flight is blocked once matches exist (Phase 3)."""
    link = await get_link(session, user_id, game)
    if link is None:
        raise LinkError("not_linked", f"No {game} account is linked.", status_code=404)
    await session.delete(link)
    await session.flush()
