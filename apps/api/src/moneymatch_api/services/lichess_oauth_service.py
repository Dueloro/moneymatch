"""Ownership-verified Lichess linking: Authorization Code + PKCE.

The access token is used once to read the account, then revoked; nothing is stored.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import now
from ..config import Settings
from ..errors import APIError
from ..models.lichess_oauth import LichessOAuthState
from ..models.linked_account import LinkedAccount
from ..models.user import User
from . import linking_service
from .hosts import lichess
from .hosts.errors import HostError, HostUnavailable

log = structlog.get_logger(__name__)

GAME = "chess.lichess"
STATE_TTL = timedelta(minutes=10)
CALLBACK_PATH = "/link/lichess/callback"


def redirect_uri(settings: Settings) -> str:
    return settings.cors_origins[0].rstrip("/") + CALLBACK_PATH


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


async def start(session: AsyncSession, user: User, settings: Settings) -> str:
    """Record a pending attempt and return the Lichess authorize URL."""
    if await linking_service.get_link(session, user.id, GAME) is not None:
        raise APIError(
            "already_linked",
            "You already have a Lichess account linked.",
            status_code=409,
        )
    await session.execute(
        delete(LichessOAuthState).where(
            (LichessOAuthState.expires_at < now())
            | (LichessOAuthState.user_id == user.id)
        )
    )
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    session.add(
        LichessOAuthState(
            state=state,
            user_id=user.id,
            code_verifier=verifier,
            expires_at=now() + STATE_TTL,
        )
    )
    await session.flush()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.lichess_oauth_client_id,
            "redirect_uri": redirect_uri(settings),
            "code_challenge_method": "S256",
            "code_challenge": _challenge(verifier),
            "state": state,
        }
    )
    return f"{lichess.LICHESS_OAUTH_AUTHORIZE}?{query}"


def _state_invalid() -> APIError:
    return APIError(
        "oauth_state_invalid",
        "That Lichess sign-in expired or wasn't started here. Try again.",
        status_code=400,
    )


def _host_unavailable() -> APIError:
    return APIError(
        "host_unavailable",
        "Lichess is unavailable right now. Try again shortly.",
        status_code=502,
    )


async def _consume(session: AsyncSession, user: User, state: str) -> str:
    """Delete the caller's state (single use, committed before any host call)."""
    row = (
        await session.execute(
            delete(LichessOAuthState)
            .where(
                LichessOAuthState.state == state,
                LichessOAuthState.user_id == user.id,
            )
            .returning(LichessOAuthState.code_verifier, LichessOAuthState.expires_at)
        )
    ).first()
    await session.commit()
    if row is None or row.expires_at <= now():
        raise _state_invalid()
    return row.code_verifier


async def _confirmed_username(code: str, verifier: str, settings: Settings) -> str:
    try:
        token = await lichess.exchange_oauth_code(
            code, verifier, redirect_uri(settings), settings.lichess_oauth_client_id
        )
    except HostUnavailable as exc:
        raise _host_unavailable() from exc
    except HostError as exc:
        log.info("lichess_oauth.code_rejected", error=str(exc))
        raise APIError(
            "oauth_denied",
            "Lichess didn't confirm the account. Try again.",
            status_code=400,
        ) from exc
    try:
        account = await lichess.get_account(token)
    except HostError as exc:
        raise _host_unavailable() from exc
    finally:
        try:
            await lichess.revoke_token(token)
        except HostError as exc:
            log.warning("lichess_oauth.revoke_failed", error=str(exc))
    username = account.get("username")
    if not isinstance(username, str) or not username:
        raise _host_unavailable()
    return username


async def complete(
    session: AsyncSession, user: User, code: str, state: str, settings: Settings
) -> LinkedAccount:
    verifier = await _consume(session, user, state)
    username = await _confirmed_username(code, verifier, settings)
    return await linking_service.bind(session, user, GAME, username, method="oauth")
