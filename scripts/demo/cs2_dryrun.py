"""Exercise all three CS2 contest modes against the live database, then roll back.

The point is to see what the demo *actually* does, rather than what the code
looks like it should do. Every mode runs the same sequence its router runs, in
the same order, inside a savepoint that is discarded afterwards, so this is safe
to run against a live database and leaves nothing behind.

    python scripts/demo/cs2_dryrun.py            # default: cs2.faceit / cs2_kd_ratio
    python scripts/demo/cs2_dryrun.py --game chess.lichess --metric chess_moves

Requires the API environment (DATABASE_URL and friends). Run it from the repo
root with the api venv, e.g.

    apps/api/.venv/Scripts/python.exe scripts/demo/cs2_dryrun.py
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "src"
sys.path.insert(0, str(SRC))

from sqlalchemy import select  # noqa: E402

from moneymatch_api.db.session import get_sessionmaker  # noqa: E402
from moneymatch_api.models.user import User  # noqa: E402
from moneymatch_api.services import (  # noqa: E402
    matchmaking,
    pool_engine,
    test_opponents,
    tournament_engine,
)

DIFFICULTIES = ("easy", "medium", "hard")


def line(text: str = "") -> None:
    print(text, flush=True)


async def pools(session, user, game: str, metric: str, entry: int) -> None:
    line("\n## Solo pool")
    status = await pool_engine.poll_status(session, user)
    line(f"status before: {status.status}")

    for difficulty in DIFFICULTIES:
        savepoint = await session.begin_nested()
        try:
            if status.status != "idle":
                await pool_engine.cancel(session, user)
            joined = await test_opponents.fill_pool(
                session,
                user,
                game=game,
                metric=metric,
                difficulty=difficulty,
                entry_cents=entry,
            )
            result = await pool_engine.enqueue(
                session,
                user,
                game=game,
                metric=metric,
                difficulty=difficulty,
                entry_cents=entry,
            )
            pool = result.pool
            detail = (
                f"room_size={pool.room_size} room_bar={pool.room_bar} "
                f"pot=${pool.pot_cents / 100:.2f}"
                if pool is not None
                else "no room"
            )
            line(f"  {difficulty:<7} opponents={joined} {result.status:<9} {detail}")
        except Exception as exc:  # noqa: BLE001 - a dry run reports, never raises
            line(f"  {difficulty:<7} FAILED {type(exc).__name__}: {exc}")
        finally:
            await savepoint.rollback()

    preview = await pool_engine.preview_bars(session, user, game, metric)
    line(f"  preview: provisional={preview['provisional']} n={preview['n']}")
    for card in preview["cards"]:
        line(
            f"    {card['difficulty']:<7} bar={card['bar']:<8} "
            f"clears {card['clear_rate'] * 100:.0f}%"
        )


async def tournaments(session, user, game: str, metric: str, entry: int) -> None:
    line("\n## Tournament")
    status = await tournament_engine.poll_status(session, user)
    line(f"status before: {status.status}")
    if status.tournament is not None:
        existing = status.tournament
        line(
            f"  already in: game={existing.game} metric={existing.ranking_metric} "
            f"state={existing.state}"
        )

    savepoint = await session.begin_nested()
    try:
        await tournament_engine.cancel(session, user)
        await tournament_engine.enqueue(
            session, user, game=game, metric=metric, entry_cents=entry
        )
        joined = await test_opponents.fill_tournament(
            session, user, game=game, metric=metric, entry_cents=entry
        )
        result = await tournament_engine.poll_status(session, user)
        tournament = result.tournament
        line(f"  opponents={joined} status={result.status}")
        if tournament is not None:
            line(
                f"  game={tournament.game} metric={tournament.ranking_metric} "
                f"state={tournament.state} pot=${tournament.pot_cents / 100:.2f}"
            )
    except Exception as exc:  # noqa: BLE001
        line(f"  FAILED {type(exc).__name__}: {exc}")
    finally:
        await savepoint.rollback()


async def head_to_head(session, user, game: str, entry: int) -> None:
    from moneymatch_api.services.markets import MARKETS

    line("\n## Head to head")
    for market in [m for m in MARKETS if m.game == game]:
        savepoint = await session.begin_nested()
        try:
            await matchmaking.cancel(session, user)
            speed = "blitz" if market.requires_speed else None
            await matchmaking.enqueue(
                session,
                user,
                game=game,
                market_key=market.key,
                speed=speed,
                entry_cents=entry,
            )
            joined = await test_opponents.fill_queue(
                session,
                user,
                game=game,
                market=market.key,
                speed=speed,
                entry_cents=entry,
            )
            status = await matchmaking.poll_status(session, user)
            line(
                f"  {market.key:<14} kind={market.kind:<10} "
                f"opponents={joined} status={getattr(status, 'status', status)}"
            )
        except Exception as exc:  # noqa: BLE001
            line(f"  {market.key:<14} FAILED {type(exc).__name__}: {exc}")
        finally:
            await savepoint.rollback()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="cs2.faceit")
    parser.add_argument("--metric", default="cs2_kd_ratio")
    parser.add_argument("--user", default="demo")
    parser.add_argument("--entry-cents", type=int, default=1000)
    parser.add_argument(
        "--no-seed",
        dest="seed_demo_fixture",
        action="store_false",
        help="skip the demo login fixture, to see the raw stored state",
    )
    args = parser.parse_args()

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user = await session.scalar(
            select(User).where(User.username == args.user)
        )
        if user is None:
            line(f"no such user: {args.user}")
            return

        line(f"# {args.game} dry run")
        line(
            f"user={args.user} metric={args.metric} "
            f"entry=${args.entry_cents / 100:.2f}"
        )
        line(f"practice opponents enabled: {test_opponents.is_enabled(user)}")

        # Logging in is what seeds the demo's baselines, and a metric bootstrap
        # over the synthetic host handle zeroes them again (n=0 reads as
        # provisional and hides every card). Running the same fixture the login
        # runs makes this script show what a user actually meets, instead of
        # whatever state the last script left behind.
        if args.seed_demo_fixture:
            from moneymatch_api.routers.demo import _ensure_demo_fixture

            await _ensure_demo_fixture(session, user)
            line("seeded the demo fixture (same call /demo/login makes)")

        await pools(session, user, args.game, args.metric, args.entry_cents)
        await tournaments(session, user, args.game, args.metric, args.entry_cents)
        await head_to_head(session, user, args.game, args.entry_cents)

        await session.rollback()
        line("\n(rolled back, nothing persisted)")


if __name__ == "__main__":
    asyncio.run(main())
