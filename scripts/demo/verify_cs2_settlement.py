"""Prove the CS2 loop: paste a share code, watch a wager settle.

Joins a solo pool with practice opponents, submits a share code through the real
intake path, and runs the grade-and-settle sequence the settlement worker runs.

Everything here is the real code except the Game Coordinator itself, which is
stood in for by `mock_gc_sidecar.py` speaking the same protocol. So this proves
the client, the four fraud checks, storage, the adapter and settlement. It does
not prove that Valve returns what we think it does; only a real GC can.

    # in one shell
    python scripts/demo/mock_gc_sidecar.py --steam-id <your steamid> --secret <secret>
    # in another
    python scripts/demo/verify_cs2_settlement.py --steam-id <your steamid>
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "src"
sys.path.insert(0, str(SRC))

from sqlalchemy import delete, select  # noqa: E402

from moneymatch_api.db.session import get_sessionmaker  # noqa: E402
from moneymatch_api.models.cs2 import Cs2Match  # noqa: E402
from moneymatch_api.models.pools import SoloEntry  # noqa: E402
from moneymatch_api.models.user import User  # noqa: E402
from moneymatch_api.services import (  # noqa: E402
    cs2_submission,
    gc_client,
    linking_service,
    pool_engine,
    telemetry_fetch,
    test_opponents,
    wallet_service,
)

GAME = "cs2.steam"
METRIC = "cs2_kd_ratio"
ENTRY = 1000


def line(text: str = "") -> None:
    print(text, flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--share-code", default="CSGO-UxSfp-RRcZ4-hp5uP-9ntcq-oXc3K")
    parser.add_argument("--user", default="demo")
    parser.add_argument("--difficulty", default="easy")
    args = parser.parse_args()

    health = await gc_client.health()
    line(f"match service ready: {health.ready}")
    if not health.ready:
        line("Start the sidecar (real or mock) first.")
        raise SystemExit(1)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user = await session.scalar(select(User).where(User.username == args.user))
        link = await linking_service.get_link(session, user.id, GAME)
        if link is None:
            line(f"{args.user} has no {GAME} link. Sign in through Steam first.")
            raise SystemExit(1)
        steam_id = link.host_account_id
        line(f"steam id: {steam_id}")

        # A share code is single use by design, so a repeat run needs the old
        # row gone. Only ever the code under test.
        await session.execute(
            delete(Cs2Match).where(Cs2Match.share_code == args.share_code)
        )

        wallet = await wallet_service.get_wallet(session, user.id)
        before = wallet.available_cents
        line(f"balance before:       ${before / 100:,.2f}")

        # 1. Join a pool with practice opponents, exactly as the router does.
        await pool_engine.cancel(session, user)
        await test_opponents.fill_pool(
            session,
            user,
            game=GAME,
            metric=METRIC,
            difficulty=args.difficulty,
            entry_cents=ENTRY,
        )
        result = await pool_engine.enqueue(
            session,
            user,
            game=GAME,
            metric=METRIC,
            difficulty=args.difficulty,
            entry_cents=ENTRY,
        )
        pool = result.pool
        if pool is None:
            line("no room formed")
            await session.rollback()
            raise SystemExit(1)
        await session.commit()
        line(
            f"room formed:          size={pool.room_size} bar={pool.room_bar} "
            f"pot=${pool.pot_cents / 100:,.2f}"
        )

        # 2. Submit the share code through the real intake path.
        match = await cs2_submission.submit(
            session,
            user_id=user.id,
            steam_id=steam_id,
            share_code=args.share_code,
        )
        await session.commit()
        stat_line = match.line_for(steam_id) or {}
        line(
            f"match accepted:       {stat_line.get('kills')}/{stat_line.get('deaths')} "
            f"({stat_line.get('headshots')} hs) over {match.rounds_total} rounds"
        )

        # 3. Grade and settle, the worker's own sequence.
        entries = list(
            await session.scalars(
                select(SoloEntry).where(SoloEntry.pool_id == pool.id)
            )
        )
        grades = await telemetry_fetch.grade_pool(session, pool, entries)
        for entry in entries:
            grade = grades.get(entry.user_id)
            who = "you" if entry.user_id == user.id else "practice"
            line(f"    {who:9s} cleared={grade.cleared if grade else None}")

        settled = await pool_engine.settle_pool(session, pool, grades)
        await session.commit()

        wallet = await wallet_service.get_wallet(session, user.id)
        after = wallet.available_cents
        line(f"pool state:           {settled.state}")
        line(f"balance after:        ${after / 100:,.2f}")
        line(f"net:                  ${(after - before) / 100:+,.2f}")

        ok = settled.state == "SETTLED" and after > before
        line("\nPASS: a pasted share code settled a real wager" if ok else "\nFAIL")
        if not ok:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
