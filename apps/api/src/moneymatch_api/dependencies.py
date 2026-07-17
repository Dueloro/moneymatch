"""Shared FastAPI dependencies (auth → provisioned user)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import verify_token
from .db.session import get_session
from .errors import APIError
from .models.user import User
from .services.user_service import get_or_create_user


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Verify the Supabase JWT and resolve/create the user row (first authed call)."""
    identity = verify_token(_bearer(authorization))
    user = await get_or_create_user(session, identity)
    request.state.user = user
    # A plain-string copy the request-log middleware can read after the session
    # has closed (the ORM instance is detached by then).
    request.state.user_id = str(user.id)
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Gate every `/admin/*` route on `users.role == 'admin'` (09-phase-6 · d.1).

    A non-admin (the default for every provisioned user) gets a clean 403 before
    any handler runs, so no admin surface is reachable without the role.
    """
    if user.role != "admin":
        raise APIError(
            "forbidden",
            "Admin access required.",
            status_code=403,
        )
    return user


def _bearer(authorization: str | None) -> str:
    from .auth import extract_bearer_token

    return extract_bearer_token(authorization)


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
