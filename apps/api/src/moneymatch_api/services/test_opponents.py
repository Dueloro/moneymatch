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
from ..models.wallet import Limit
from . import demo_mode, linking_service, skill_prior
from .user_service import provision_new_user

log = structlog.get_logger(__name__)

#: Daily caps for a practice opponent: high enough that the scaffolding never
#: refuses itself, and irrelevant either way since none of this is real money.
_BOT_CAP_CENTS = 100_000_000

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
    """Practice opponents are available for the shared demo account, and — in a
    **simulation test build** (`demo_simulate_enabled`) — for any signed-in user,
    so a real signup can exercise pools / 1v1 without a second human. Both gates
    are off in real production, so the production path never sees a fabricated
    opponent.
    """
    if demo_mode.is_demo_user(user):
        return True
    from ..config import get_settings

    return bool(get_settings().demo_simulate_enabled)


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

    # Responsible-gambling caps exist to protect a person from themselves. A
    # fabricated opponent has nobody to protect, and the default daily *loss*
    # cap quietly broke the demo: the two opponents built to miss lose their
    # entry every single room, so after a few pools they were refused for
    # exceeding it. The matcher then found nobody to pair the demo with and
    # fell back to a room of one, with no pot to split and nothing on screen
    # explaining why.
    #
    # Raised as data rather than as an exemption inside `limits_service`, so
    # nothing in the money path grows a branch that could ever apply to a real
    # account.
    limits = await session.scalar(select(Limit).where(Limit.user_id == user.id))
    if limits is not None:
        limits.daily_loss_cap_cents = max(limits.daily_loss_cap_cents, _BOT_CAP_CENTS)
        limits.daily_entry_cap_cents = max(limits.daily_entry_cap_cents, _BOT_CAP_CENTS)
        await session.flush()

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
    # A complete ProfileSnapshot shape — matchmaking reconstructs a ProfileSnapshot
    # from this for the chess (Elo-band) 1v1 path, which validates every field.
    rating_int = int(rating) if rating else 1500
    snapshot = {
        "username": handle,
        "display_name": handle,
        "url": f"https://lichess.org/@/{handle}",
        "link_method": "username",
        "game": game,
        "win_rate": 0.5,
        "draw_rate": 0.0,
        "total_games": 20,
        "primary_speed": "bullet",
        "formats": [
            {"speed": "bullet", "rating": rating_int, "games": 20, "provisional": False}
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
    for handle in _HANDLES:
        if len(opponents) >= count:
            break
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


def graded_as_failed(host_account_id: str) -> bool:
    """True for a practice opponent's contest entry, which always forfeits.

    A real entrant with no qualifying match is *unverifiable* and gets refunded,
    because we cannot prove they failed. A dummy has no host account at all, so
    grading it as a forfeit (ranked last, paid nothing) is what makes the stake
    real, so beating the bots actually pays out of their entries.

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
    "fill_queue",
    "is_enabled",
    "purge",
    "test_user_filter",
]
