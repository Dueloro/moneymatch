"""Demo account behaviour: the sandbox where the product can be exercised solo.

"Skip sign-up, enter the demo" lands on one shared account (`DEMO_AUTH_ID`).
That account is the **testing surface**, and it differs from a real account in
exactly two ways:

- **Contests fill themselves.** Joining a pool, tournament or duel pulls in
  throwaway practice opponents, because nothing forms with a single player and
  none of the fetch / grade / settle path could otherwise run. See
  `test_opponents.py`.
- **Casual games count.** Baselines, pool bars and tournament scores read
  unrated games too, which includes games against the Lichess computer. That is
  the quickest way to produce a finished game on demand.

Everyone who signs in normally gets production behaviour: rated games only, and
no fabricated opponents. Both live in the same deployment, so the sign-in path
is continuously exercised as the real thing while the demo stays a sandbox. Turn
off demo login (`DEMO_LOGIN_ENABLED=false`) and the testing behaviour disappears
with it, leaving production untouched.

This replaced a pair of environment switches. Those applied to the whole
deployment, so testing and production behaviour could never coexist, and
flipping one for a test changed the rules for real users too.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import DEMO_AUTH_ID, rated_only_game
from ..models.user import User


def is_demo_user(user: User) -> bool:
    """True for the shared demo account, false for every real signup."""
    return user.auth_id == DEMO_AUTH_ID


async def demo_user_id(session: AsyncSession) -> uuid.UUID | None:
    """The demo account's id, or None when demo login has never been used."""
    return await session.scalar(select(User.id).where(User.auth_id == DEMO_AUTH_ID))


async def is_demo_user_id(session: AsyncSession, user_id: uuid.UUID) -> bool:
    demo = await demo_user_id(session)
    return demo is not None and demo == user_id


async def rated_only_for(session: AsyncSession, user_id: uuid.UUID, game: str) -> bool:
    """Whether this user's stats for `game` should be built from rated games only.

    Only rated-only games (chess) filter, and never for the demo account.
    Callers pass the result into `GameFilters(rated_only=...)`, so the same code
    path serves both.
    """
    if not rated_only_game(game):
        return False
    return not await is_demo_user_id(session, user_id)


__all__ = [
    "demo_user_id",
    "is_demo_user",
    "is_demo_user_id",
    "rated_only_for",
]
