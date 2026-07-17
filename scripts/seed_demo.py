#!/usr/bin/env python
"""Stand up a demoable MoneyMatch environment in one command (09-phase-6 · d.5).

Creates a set of demo users (an admin + N players) each with a provisioned wallet
+ signup grant, a linked CS2 fixture account, and non-provisional metric models;
then a few open queue tickets, an open solo pool with entries, and an open
tournament — enough to click through Play / Pools / Tournament / Activity / the
admin surface immediately. Used by the e2e suite too.

Run in the API venv so `moneymatch_api` + `DATABASE_URL` resolve:

    cd apps/api && uv run python ../../scripts/seed_demo.py
    cd apps/api && uv run python ../../scripts/seed_demo.py --players 6

Idempotent and non-destructive: demo users/links are reused if they already
exist (never re-granted), open tickets are refreshed each run, and a pool /
tournament is created only if the demo cohort has none in flight — so re-running
is safe and the ledger's solvency invariant always holds. It never touches real
accounts.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

_API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from moneymatch_api.constants import GAME_CS2_FACEIT  # noqa: E402
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
CS2_METRIC = "cs2_kd_ratio"
ENTRY = 1_000  # $10
RAKE_BPS = 1_000  # 10%


async def _get_or_create_user(
    session: AsyncSession, handle: str, *, admin: bool = False, linked: bool = True
) -> User:
    """Reuse an existing demo user (already provisioned + linked) or create one.

    Reuse avoids a second signup grant — the ledger's solvency invariant stays
    intact across re-runs."""
    existing = await session.scalar(
        select(User).where(User.auth_id == f"{SEED_PREFIX}{handle}")
    )
    if existing is not None:
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
        session.add(
            LinkedAccount(
                user_id=user.id,
                game=GAME_CS2_FACEIT,
                host_account_id=f"faceit_{handle}",
                host_username=handle,
                profile_snapshot={"username": handle, "game": GAME_CS2_FACEIT},
            )
        )
        session.add(
            MetricModel(
                user_id=user.id,
                game=GAME_CS2_FACEIT,
                metric=CS2_METRIC,
                mu=1.05,
                sigma=0.2,
                n=25,  # non-provisional (>= 10)
            )
        )
        await session.flush()
    return user


async def _linked_id(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    return await session.scalar(
        select(LinkedAccount.id).where(LinkedAccount.user_id == user_id)
    )


async def _seed(players: int) -> None:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    created_pool = created_tourney = False
    try:
        async with sm() as session:
            await _get_or_create_user(session, "admin", admin=True, linked=False)
            users = [
                await _get_or_create_user(session, f"player{i}")
                for i in range(1, players + 1)
            ]
            await session.commit()

            # --- Open H2H queue tickets (refresh: drop old, add fresh) -------- #
            user_ids = [u.id for u in users]
            await session.execute(
                delete(QueueTicket).where(QueueTicket.user_id.in_(user_ids))
            )
            for u in users[:2]:
                link_id = await _linked_id(session, u.id)
                session.add(
                    QueueTicket(
                        user_id=u.id,
                        linked_account_id=link_id,
                        game=GAME_CS2_FACEIT,
                        product="duel",
                        market="kd_ratio",
                        entry_cents=ENTRY,
                        baseline_snapshot={
                            CS2_METRIC: {"mu": 1.05, "sigma": 0.2, "n": 25}
                        },
                        state="waiting",
                        expires_at=now + timedelta(minutes=10),
                    )
                )
            await session.commit()

            # --- An OPEN solo pool with entries (a "room") — only if none ---- #
            pool_members = users[: min(3, len(users))]
            has_pool = await session.scalar(
                select(SoloEntry.id)
                .join(SoloPool, SoloPool.id == SoloEntry.pool_id)
                .where(SoloEntry.user_id.in_(user_ids), SoloPool.state == "LOCKED")
                .limit(1)
            )
            if not has_pool and len(pool_members) >= 2:
                split = money_math.split_pot(ENTRY * len(pool_members), 1, RAKE_BPS)
                pool = SoloPool(
                    game=GAME_CS2_FACEIT,
                    metric=CS2_METRIC,
                    difficulty="medium",
                    room_bar=1.25,
                    entry_cents=ENTRY,
                    rake_bps=RAKE_BPS,
                    room_size=len(pool_members),
                    min_entrants=2,
                    pot_cents=ENTRY * len(pool_members),
                    prize_cents=split.payouts_cents[0],
                    rake_cents=split.rake_cents,
                    state="LOCKED",
                    window_starts_at=now,
                    window_ends_at=now + timedelta(hours=24),
                )
                session.add(pool)
                await session.flush()
                for u in pool_members:
                    session.add(
                        SoloEntry(
                            pool_id=pool.id,
                            user_id=u.id,
                            linked_account_id=await _linked_id(session, u.id),
                            host_account_id=f"faceit_{u.username}",
                            personal_bar=1.25,
                            baseline_snapshot={
                                CS2_METRIC: {"mu": 1.05, "sigma": 0.2, "n": 25}
                            },
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
                created_pool = True
                await session.commit()

            # --- An OPEN tournament with entries — only if none in flight ---- #
            field = users[: min(6, len(users))]
            has_tourney = await session.scalar(
                select(TournamentEntry.id)
                .join(Tournament, Tournament.id == TournamentEntry.tournament_id)
                .where(
                    TournamentEntry.user_id.in_(user_ids),
                    Tournament.state == "LOCKED",
                )
                .limit(1)
            )
            if not has_tourney and len(field) >= 2:
                tsplit = money_math.split_pot(ENTRY * len(field), 1, RAKE_BPS)
                tourney = Tournament(
                    game=GAME_CS2_FACEIT,
                    ranking_metric=CS2_METRIC,
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
                            linked_account_id=await _linked_id(session, u.id),
                            host_account_id=f"faceit_{u.username}",
                            baseline_snapshot={
                                CS2_METRIC: {"mu": 1.05, "sigma": 0.2, "n": 25}
                            },
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
                created_tourney = True
                await session.commit()

        print(
            f"ok: {players} players + 1 admin ready · 2 open tickets · "
            f"pool {'created' if created_pool else 'exists'} · "
            f"tournament {'created' if created_tourney else 'exists'}"
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
