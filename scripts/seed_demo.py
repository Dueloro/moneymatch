#!/usr/bin/env python
"""Stand up a demoable MoneyMatch environment in one command (09-phase-6 · d.5).

Creates a set of demo users (an admin + N players) each with a provisioned wallet
+ signup grant, a linked host account **per game**, and non-provisional metric
models; then, **for every registered game**, a few open H2H queue tickets, an
open solo pool with entries, and an open tournament — enough to click through
Play / Pools / Tournament / Activity / the admin surface immediately, on any
game. Used by the e2e suite too.

Run in the API venv so `moneymatch_api` + `DATABASE_URL` resolve:

    cd apps/api && uv run python ../../scripts/seed_demo.py
    cd apps/api && uv run python ../../scripts/seed_demo.py --players 6

Idempotent and non-destructive: demo users/links/models are reused if they
already exist (never re-granted), open tickets are refreshed each run, and a
pool / tournament is created only if the demo cohort has none in flight *for
that game* — so re-running is safe (existing CS2-only demo cohorts pick up the
other games) and the ledger's solvency invariant always holds. It never touches
real accounts.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from moneymatch_api.constants import (  # noqa: E402
    GAME_CHESS_LICHESS,
    GAME_CS2_FACEIT,
    GAME_DOTA2_OPENDOTA,
    GAME_PUBG_STEAM,
)
from moneymatch_api.db.session import (  # noqa: E402
    dispose_engine,
    get_sessionmaker,
)
from moneymatch_api.models.linked_account import LinkedAccount  # noqa: E402
from moneymatch_api.models.play import QueueTicket  # noqa: E402
from moneymatch_api.models.pools import SoloEntry, SoloPool  # noqa: E402
from moneymatch_api.models.skill import MetricModel  # noqa: E402
from moneymatch_api.models.tournaments import (  # noqa: E402
    Tournament,
    TournamentEntry,
)
from moneymatch_api.models.user import User  # noqa: E402
from moneymatch_api.services import (  # noqa: E402
    money_math,
    user_service,
    wallet_service,
)

SEED_PREFIX = "seed_"
ENTRY = 1_000  # $10
RAKE_BPS = 1_000  # 10%


@dataclass(frozen=True)
class GameFixture:
    """Per-game demo config: how to link accounts and what to wager on.

    `metric` is the pool/tournament ranking stat (and the H2H stat for stat-race
    games). `h2h_stat` distinguishes a stat duel (CS2/Dota2/PUBG) from chess's
    brokered `win_h2h`, which grades on the game result and needs a time control
    (`h2h_speed`) + an Elo `rating` baseline instead of a metric model.
    """

    game: str
    host_prefix: str  # host_account_id / host_username prefix (unique per game)
    metric: str  # pool/tournament metric — chess_accuracy is a demo-seeded baseline
    mu: float
    sigma: float
    n: int  # >= METRIC_PROVISIONAL_MIN_N so it's non-provisional
    bar: float  # room_bar / personal_bar, in the metric's units
    h2h_market: str  # queue-ticket market key (services/markets.py)
    h2h_stat: bool  # True → stat_race duel; False → chess win_h2h
    h2h_speed: str | None = None  # chess time control
    rating: int | None = None  # chess Elo baseline (for the H2H band)


# One fixture per registered, playable game (constants.REGISTERED_GAMES).
FIXTURES: tuple[GameFixture, ...] = (
    GameFixture(
        game=GAME_CHESS_LICHESS,
        host_prefix="lichess",
        metric="chess_accuracy",
        mu=82.0,
        sigma=4.0,
        n=30,
        bar=80.0,
        h2h_market="win_h2h",
        h2h_stat=False,
        h2h_speed="blitz",
        rating=1500,
    ),
    GameFixture(
        game=GAME_CS2_FACEIT,
        host_prefix="faceit",
        metric="cs2_kd_ratio",
        mu=1.05,
        sigma=0.2,
        n=25,
        bar=1.25,
        h2h_market="kd_ratio",
        h2h_stat=True,
    ),
    GameFixture(
        game=GAME_DOTA2_OPENDOTA,
        host_prefix="opendota",
        metric="dota2_kda_ratio",
        mu=3.2,
        sigma=0.6,
        n=25,
        bar=3.0,
        h2h_market="kda_ratio",
        h2h_stat=True,
    ),
    GameFixture(
        game=GAME_PUBG_STEAM,
        host_prefix="pubg",
        metric="pubg_kills",
        mu=4.5,
        sigma=1.2,
        n=25,
        bar=5.0,
        h2h_market="kills",
        h2h_stat=True,
    ),
)


def _baseline(fx: GameFixture) -> dict:
    """Frozen metric-model snapshot for a stat-based entry (pool/tournament/duel)."""
    return {fx.metric: {"mu": fx.mu, "sigma": fx.sigma, "n": fx.n}}


async def _get_or_create_user(
    session: AsyncSession, handle: str, *, admin: bool = False, linked: bool = True
) -> User:
    """Reuse an existing demo user (already provisioned) or create one.

    Reuse avoids a second signup grant — the ledger's solvency invariant stays
    intact across re-runs. Per-game links/models are ensured separately (and
    idempotently) by `_ensure_game_setup`, so a pre-existing CS2-only cohort
    gains the other games on re-run."""
    existing = await session.scalar(
        select(User).where(User.auth_id == f"{SEED_PREFIX}{handle}")
    )
    if existing is not None:
        if linked:
            await _ensure_game_setup(session, existing)
        return existing

    user = User(
        auth_id=f"{SEED_PREFIX}{handle}",
        username=handle,
        email=f"{handle}@demo.moneymatch.test",
        residence_state="MA",
        dob_attested_18plus=True,
        role="admin" if admin else "user",
    )
    session.add(user)
    await session.flush()
    await user_service.provision_new_user(session, user)  # wallet + $1,000 grant

    if linked:
        await _ensure_game_setup(session, user)
    return user


async def _ensure_game_setup(session: AsyncSession, user: User) -> None:
    """Ensure this user has a linked account + metric model for every game.

    Idempotent: only inserts what's missing, so re-running (or upgrading a
    CS2-only demo user) never violates the `(user_id, game)` /
    `(user_id, game, metric)` uniqueness rules."""
    for fx in FIXTURES:
        have_link = await session.scalar(
            select(LinkedAccount.id).where(
                LinkedAccount.user_id == user.id, LinkedAccount.game == fx.game
            )
        )
        if have_link is None:
            snapshot: dict = {"username": user.username, "game": fx.game}
            if fx.rating is not None:
                snapshot["rating"] = fx.rating
            session.add(
                LinkedAccount(
                    user_id=user.id,
                    game=fx.game,
                    host_account_id=f"{fx.host_prefix}_{user.username}",
                    host_username=user.username,
                    profile_snapshot=snapshot,
                )
            )
        have_model = await session.scalar(
            select(MetricModel.id).where(
                MetricModel.user_id == user.id,
                MetricModel.game == fx.game,
                MetricModel.metric == fx.metric,
            )
        )
        if have_model is None:
            session.add(
                MetricModel(
                    user_id=user.id,
                    game=fx.game,
                    metric=fx.metric,
                    mu=fx.mu,
                    sigma=fx.sigma,
                    n=fx.n,  # non-provisional (>= 10)
                )
            )
    await session.flush()


async def _linked_id(session: AsyncSession, user_id: uuid.UUID, game: str) -> uuid.UUID:
    return await session.scalar(
        select(LinkedAccount.id).where(
            LinkedAccount.user_id == user_id, LinkedAccount.game == game
        )
    )


async def _seed_tickets(
    session: AsyncSession, users: list[User], fx: GameFixture, now: datetime
) -> int:
    """Two open H2H tickets for this game (refresh: callers drop old first)."""
    if fx.h2h_stat:
        baseline = _baseline(fx)
    else:  # chess win_h2h — Elo-band baseline, no metric model
        baseline = {"rating": fx.rating}
    n = 0
    for u in users[:2]:
        session.add(
            QueueTicket(
                user_id=u.id,
                linked_account_id=await _linked_id(session, u.id, fx.game),
                game=fx.game,
                product="duel",
                market=fx.h2h_market,
                speed=fx.h2h_speed,
                entry_cents=ENTRY,
                baseline_snapshot=baseline,
                state="waiting",
                expires_at=now + timedelta(minutes=10),
            )
        )
        n += 1
    return n


async def _seed_pool(
    session: AsyncSession,
    users: list[User],
    user_ids: list[uuid.UUID],
    fx: GameFixture,
    now: datetime,
) -> bool:
    """An OPEN (LOCKED) solo pool with escrowed entries — only if none for this game."""
    members = users[: min(3, len(users))]
    has_pool = await session.scalar(
        select(SoloEntry.id)
        .join(SoloPool, SoloPool.id == SoloEntry.pool_id)
        .where(
            SoloEntry.user_id.in_(user_ids),
            SoloPool.game == fx.game,
            SoloPool.state == "LOCKED",
        )
        .limit(1)
    )
    if has_pool or len(members) < 2:
        return False

    split = money_math.split_pot(ENTRY * len(members), 1, RAKE_BPS)
    pool = SoloPool(
        game=fx.game,
        metric=fx.metric,
        difficulty="medium",
        room_bar=fx.bar,
        entry_cents=ENTRY,
        rake_bps=RAKE_BPS,
        room_size=len(members),
        min_entrants=2,
        pot_cents=ENTRY * len(members),
        prize_cents=split.payouts_cents[0],
        rake_cents=split.rake_cents,
        state="LOCKED",
        window_starts_at=now,
        window_ends_at=now + timedelta(hours=24),
    )
    session.add(pool)
    await session.flush()
    for u in members:
        session.add(
            SoloEntry(
                pool_id=pool.id,
                user_id=u.id,
                linked_account_id=await _linked_id(session, u.id, fx.game),
                host_account_id=f"{fx.host_prefix}_{u.username}",
                personal_bar=fx.bar,
                baseline_snapshot=_baseline(fx),
                status="LOCKED",
            )
        )
        # Escrow the entry so the LOCKED pool's money trail is real
        # (reconciliation: entries == still_held while locked).
        await wallet_service.escrow_hold(
            session,
            u.id,
            ENTRY,
            ref_type="solo_pool",
            ref_id=pool.id,
            memo="seed pool entry",
        )
    return True


async def _seed_tournament(
    session: AsyncSession,
    users: list[User],
    user_ids: list[uuid.UUID],
    fx: GameFixture,
    now: datetime,
) -> bool:
    """An OPEN (LOCKED) tournament with entries — only if none for this game."""
    field = users[: min(6, len(users))]
    has_tourney = await session.scalar(
        select(TournamentEntry.id)
        .join(Tournament, Tournament.id == TournamentEntry.tournament_id)
        .where(
            TournamentEntry.user_id.in_(user_ids),
            Tournament.game == fx.game,
            Tournament.state == "LOCKED",
        )
        .limit(1)
    )
    if has_tourney or len(field) < 2:
        return False

    tsplit = money_math.split_pot(ENTRY * len(field), 1, RAKE_BPS)
    tourney = Tournament(
        game=fx.game,
        ranking_metric=fx.metric,
        entry_cents=ENTRY,
        rake_bps=RAKE_BPS,
        prize_split=[50, 30, 20],
        field_size=len(field),
        min_field=2,
        min_ranked=2,
        score_matches=3,
        pot_cents=ENTRY * len(field),
        prize_cents=tsplit.payouts_cents[0],
        rake_cents=tsplit.rake_cents,
        state="LOCKED",
        window_starts_at=now,
        window_ends_at=now + timedelta(hours=48),
    )
    session.add(tourney)
    await session.flush()
    for u in field:
        session.add(
            TournamentEntry(
                tournament_id=tourney.id,
                user_id=u.id,
                linked_account_id=await _linked_id(session, u.id, fx.game),
                host_account_id=f"{fx.host_prefix}_{u.username}",
                baseline_snapshot=_baseline(fx),
                enqueued_at=now,
                status="RANKED",
            )
        )
        await wallet_service.escrow_hold(
            session,
            u.id,
            ENTRY,
            ref_type="tournament",
            ref_id=tourney.id,
            memo="seed tournament entry",
        )
    return True


async def _seed(players: int) -> None:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    tickets = 0
    pools_created: list[str] = []
    tourneys_created: list[str] = []
    try:
        async with sm() as session:
            await _get_or_create_user(session, "admin", admin=True, linked=False)
            users = [
                await _get_or_create_user(session, f"player{i}")
                for i in range(1, players + 1)
            ]
            await session.commit()

            user_ids = [u.id for u in users]

            # --- Open H2H queue tickets, per game (refresh: drop old, add fresh) --
            await session.execute(
                delete(QueueTicket).where(QueueTicket.user_id.in_(user_ids))
            )
            for fx in FIXTURES:
                tickets += await _seed_tickets(session, users, fx, now)
            await session.commit()

            # --- An OPEN solo pool per game (only if none in flight for it) -------
            for fx in FIXTURES:
                if await _seed_pool(session, users, user_ids, fx, now):
                    pools_created.append(fx.game)
                    await session.commit()

            # --- An OPEN tournament per game (only if none in flight for it) ------
            for fx in FIXTURES:
                if await _seed_tournament(session, users, user_ids, fx, now):
                    tourneys_created.append(fx.game)
                    await session.commit()

        games = len(FIXTURES)
        print(
            f"ok: {players} players + 1 admin ready · {games} games linked · "
            f"{tickets} open tickets ({games} games) · "
            f"pools created for {pools_created or 'none (all exist)'} · "
            f"tournaments created for {tourneys_created or 'none (all exist)'}"
        )
        print("     admin handle: 'admin' (auth_id seed_admin)")
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a demoable environment.")
    parser.add_argument("--players", type=int, default=4, help="number of demo players")
    args = parser.parse_args()
    asyncio.run(_seed(args.players))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
