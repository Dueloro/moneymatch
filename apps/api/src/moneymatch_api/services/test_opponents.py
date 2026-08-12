"""Throwaway practice opponents, so one real player can exercise the real system.

**This module is scaffolding. Delete it before launch.** Everything fake in the
product lives here and in the three router call sites that reference it; nothing
else in the codebase knows these users exist.

Why it exists: pools need 3 to 4 entrants, tournaments need a field, and a
head-to-head needs a counterparty. With a single real account nothing ever
forms, so none of the Lichess fetch, grade or settle path can be exercised. The
alternative, faking rooms in the UI, would test none of that.

How it stays honest:

- Opponents are ordinary users created through the same provisioning as anyone
  else, then enqueued through the engines' own public `enqueue()`. No engine has
  a special case for them, so what you are testing is the real path.
- They are excluded from the leaderboard and from the live activity ticker, so
  they can never look like real activity to anyone.
- They never play, and at settlement they are graded as having missed their bar
  (`graded_as_failed`), so clearing yours pays out of their entries. They are
  the only entrants ever graded without being looked up; a real player who
  produces no qualifying game is unverifiable and gets refunded instead.
- `purge()` removes every one of them in a single call.

Only ever active for the shared demo account (`demo_mode.is_demo_user`), so a
real signup never sees a fabricated opponent in any environment.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import METRIC_BAR_INCREMENT
from ..models.linked_account import LinkedAccount
from ..models.skill import MetricModel
from ..models.user import User
from . import demo_mode, linking_service, skill_prior
from .user_service import provision_new_user

log = structlog.get_logger(__name__)

# Every fake row is findable by this one prefix. `purge()` relies on it.
TEST_AUTH_PREFIX = "zz_testbot_"

# Handles are deliberately obvious on screen. If you ever see one of these in a
# real contest, something is wrong.
_HANDLES = (
    "testbot_ada",
    "testbot_bo",
    "testbot_cy",
    "testbot_di",
    "testbot_eli",
    "testbot_fen",
    "testbot_gus",
    "testbot_hal",
    "testbot_ivy",
)

# Dummies mirror your baseline exactly. It is tempting to give them terrible
# stats so they "obviously lose", but the pool engine rejects a room whose
# members' implied clear probabilities are too far apart, so a zero-stat
# opponent simply fails to form a room and you learn nothing. They lose at
# settlement instead: they never play, so they miss the bar and forfeit
# (see `graded_as_failed`).
_MU_FACTOR = 1.0


def is_enabled(user: User) -> bool:
    """Only ever for the shared demo account.

    Not an environment switch and not a feature flag: this is a property of
    *who is playing*. A real signup never sees a fabricated opponent, in any
    environment, so the production path stays honest while the demo account
    stays fully exercisable. Removing demo login removes this with it.
    """
    return demo_mode.is_demo_user(user)


async def _opponent(
    session: AsyncSession,
    handle: str,
    game: str,
    host_id: str,
    rating: float | None = None,
) -> User:
    """A funded, game-linked practice opponent. Idempotent."""
    auth_id = f"{TEST_AUTH_PREFIX}{handle}"
    user = await session.scalar(select(User).where(User.auth_id == auth_id))
    if user is None:
        user = User(
            auth_id=auth_id,
            username=handle,
            email=f"{auth_id}@testbot.invalid",
            residence_state="NY",
            dob_attested_18plus=True,
        )
        session.add(user)
        await session.flush()
        await provision_new_user(session, user)  # wallet + signup grant

    linked = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id, LinkedAccount.game == game
        )
    )
    # Mirror your rating, so the prior in `skill_prior` puts the opponent's
    # baseline where yours is. Without it they read as a default 1500 player,
    # which drags the shared room bar away from the bar your own card quoted.
    # Rewritten every time rather than only on creation, so opponents left over
    # from a previous session pick your current rating up instead of holding a
    # stale one.
    snapshot = {
        "username": handle,
        "game": game,
        "primary_speed": "bullet",
        "formats": [
            {
                "speed": "bullet",
                "rating": int(rating) if rating else 1500,
                "games": 20,
            }
        ],
    }
    if linked is None:
        session.add(
            LinkedAccount(
                user_id=user.id,
                game=game,
                # A host id that cannot resolve to a real account, so a stray
                # settlement poll returns nothing rather than someone's games.
                host_account_id=host_id,
                host_username=handle,
                profile_snapshot=snapshot,
            )
        )
    else:
        linked.profile_snapshot = snapshot
    await session.flush()
    return user


async def _mirror_model(
    session: AsyncSession, opponent: User, source: MetricModel
) -> None:
    """Give the opponent a baseline just under yours on the same metric."""
    existing = await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == opponent.id,
            MetricModel.game == source.game,
            MetricModel.metric == source.metric,
        )
    )
    increment = METRIC_BAR_INCREMENT.get(source.metric, 0.01)
    mu = max(increment, float(source.mu) * _MU_FACTOR)
    if existing is None:
        session.add(
            MetricModel(
                user_id=opponent.id,
                game=source.game,
                metric=source.metric,
                mu=mu,
                sigma=float(source.sigma) or increment,
                n=max(int(source.n), 1),
            )
        )
    else:
        existing.mu = mu
        existing.sigma = float(source.sigma) or increment
        existing.n = max(int(source.n), 1)
    await session.flush()


async def _your_model(
    session: AsyncSession, user: User, game: str, metric: str
) -> MetricModel | None:
    return await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user.id,
            MetricModel.game == game,
            MetricModel.metric == metric,
        )
    )


async def _prepare(
    session: AsyncSession, user: User, game: str, metric: str | None, count: int
) -> list[User]:
    """Create `count` opponents ready to enter a contest on `game`/`metric`."""
    source = await _your_model(session, user, game, metric) if metric else None
    your_link = await linking_service.get_link(session, user.id, game)
    rating = skill_prior.host_rating(your_link) if your_link else None
    opponents: list[User] = []
    for handle in _HANDLES[:count]:
        opponent = await _opponent(
            session,
            handle,
            game,
            host_id=f"{TEST_AUTH_PREFIX}{handle}",
            rating=rating,
        )
        if source is not None:
            await _mirror_model(session, opponent, source)
        opponents.append(opponent)
    return opponents


async def fill_pool(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    metric: str,
    difficulty: str,
    entry_cents: int,
    count: int = 3,
) -> int:
    """Enter `count` opponents into the same pool bucket you just joined.

    Uses `pool_engine.enqueue`, the same entrypoint the API uses for you, so the
    room forms through the real composition and escrow path.
    """
    from . import pool_engine  # local: the engine must not import this module

    joined = 0
    for opponent in await _prepare(session, user, game, metric, count):
        try:
            # Drop any ticket left in another bucket first. A waiting ticket is
            # per user, not per bucket, so a bot still queued for last attempt's
            # difficulty or entry would be handed straight back instead of
            # joining yours, and your room would form with only you in it.
            await pool_engine.cancel(session, opponent)
            await pool_engine.enqueue(
                session,
                opponent,
                game=game,
                metric=metric,
                difficulty=difficulty,
                entry_cents=entry_cents,
            )
            joined += 1
        except Exception as exc:  # noqa: BLE001 - scaffolding must never 500 you
            log.warning(
                "testbot.pool_join_failed", handle=opponent.username, error=str(exc)
            )
    log.info("testbot.pool_filled", joined=joined, metric=metric)
    return joined


async def fill_tournament(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    metric: str,
    entry_cents: int,
    count: int = 9,
) -> int:
    """Enter `count` opponents into the tournament field you just joined."""
    from . import tournament_engine

    joined = 0
    for opponent in await _prepare(session, user, game, metric, count):
        try:
            await tournament_engine.cancel(session, opponent)
            await tournament_engine.enqueue(
                session,
                opponent,
                game=game,
                metric=metric,
                entry_cents=entry_cents,
            )
            joined += 1
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "testbot.tournament_join_failed",
                handle=opponent.username,
                error=str(exc),
            )
    log.info("testbot.tournament_filled", joined=joined, metric=metric)
    return joined


async def fill_queue(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    market: str,
    speed: str | None,
    entry_cents: int,
) -> int:
    """Put one opponent in the head-to-head queue so your search pairs."""
    from . import matchmaking

    opponents = await _prepare(session, user, game, None, 1)
    for opponent in opponents:
        try:
            await matchmaking.cancel(session, opponent)
            await matchmaking.enqueue(
                session,
                opponent,
                game=game,
                market_key=market,
                speed=speed,
                entry_cents=entry_cents,
            )
            log.info("testbot.queue_filled", handle=opponent.username)
            return 1
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "testbot.queue_join_failed", handle=opponent.username, error=str(exc)
            )
    return 0


#: The practice opponents that beat their bar instead of missing it.
#:
#: Every dummy missing meant a pool only ever had one possible outcome: you
#: clear and take the whole prize, or you miss and everything is refunded. The
#: rule that actually governs a pool -- clearers *split* the pot -- was never
#: reachable with one real player, so the demo could not show the thing the
#: product does.
#:
#: One clearer is enough to show both halves. Clear your bar and you split with
#: it; miss, and it takes the pot off you. Keyed by handle so it is the same
#: opponent every time: a demo whose outcome moves around is not a demo.
CLEARING_HANDLES = frozenset({"testbot_ada"})


def is_practice_opponent(host_account_id: str) -> bool:
    """True for any practice opponent, whatever it is graded as.

    Keyed off the host id rather than a user lookup, so settlement needs no
    extra query.
    """
    return host_account_id.startswith(TEST_AUTH_PREFIX)


def clears_its_bar(host_account_id: str) -> bool:
    """True for the practice opponent built to clear (see `CLEARING_HANDLES`)."""
    if not is_practice_opponent(host_account_id):
        return False
    return host_account_id[len(TEST_AUTH_PREFIX) :] in CLEARING_HANDLES


def graded_as_failed(host_account_id: str) -> bool:
    """True for a practice opponent's contest entry, which always misses its bar.

    A real entrant with no qualifying match is *unverifiable* and gets refunded,
    because we cannot prove they failed. A dummy has no host account at all, so
    refunding it would make every test pool a no-op: nobody wins, nobody loses,
    the pot goes back where it came from. Grading it as a miss is what makes the
    stake real, so clearing your bar actually pays out of their entries.

    Keyed off the host id rather than a user lookup, so settlement needs no
    extra query.
    """
    return host_account_id.startswith(TEST_AUTH_PREFIX)


def test_user_filter() -> Any:
    """SQLAlchemy predicate for excluding practice opponents from a query."""
    return ~User.auth_id.like(f"{TEST_AUTH_PREFIX}%")


async def purge(session: AsyncSession) -> int:
    """Delete every practice opponent. One call, and the fakes are gone.

    Their wallets, tickets, entries and contest rows go with them via
    `ON DELETE CASCADE`. Run this before launch, then delete this module.
    """
    ids = list(
        await session.scalars(
            select(User.id).where(User.auth_id.like(f"{TEST_AUTH_PREFIX}%"))
        )
    )
    if not ids:
        return 0
    await session.execute(delete(User).where(User.id.in_(ids)))
    await session.flush()
    log.info("testbot.purged", count=len(ids))
    return len(ids)


__all__ = [
    "TEST_AUTH_PREFIX",
    "graded_as_failed",
    "fill_pool",
    "fill_queue",
    "fill_tournament",
    "is_enabled",
    "purge",
    "test_user_filter",
]
