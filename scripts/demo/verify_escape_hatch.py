"""Prove the phase-0 escape hatch: an injected match settles a real wager.

Forms a solo pool with practice opponents, injects one finished match for the
real entrant, then runs the grade-and-settle sequence the settlement worker
runs, and checks the money actually moved.

**This commits.** It has to: the adapter reads injected matches in its own
session (it runs in the worker process too), so an uncommitted row is invisible
to the very path being tested. A rolled-back "proof" would prove nothing. What
it leaves behind is a settled pool and one simulated-match row, which is the
audit trail you want anyway — both are visible in the admin contest view and the
row is logged as `simulated=True`.

    DEMO_SIMULATE_ENABLED=1 apps/api/.venv/Scripts/python.exe \\
        scripts/demo/verify_escape_hatch.py
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import UTC, datetime

SRC = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "src"
sys.path.insert(0, str(SRC))

from sqlalchemy import select  # noqa: E402

from moneymatch_api.db.session import get_sessionmaker  # noqa: E402
from moneymatch_api.models.pools import SoloEntry  # noqa: E402
from moneymatch_api.models.user import User  # noqa: E402
from moneymatch_api.services import (  # noqa: E402
    demo_simulation,
    linking_service,
    pool_engine,
    telemetry_fetch,
    test_opponents,
    wallet_service,
)

GAME = "cs2.faceit"
METRIC = "cs2_kd_ratio"
DIFFICULTY = "medium"
ENTRY = 1000


def line(text: str = "") -> None:
    print(text, flush=True)


async def main() -> None:
    if not demo_simulation.is_enabled():
        line("DEMO_SIMULATE_ENABLED is not set, so injected results are inert.")
        line("Re-run with DEMO_SIMULATE_ENABLED=1")
        raise SystemExit(1)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user = await session.scalar(select(User).where(User.username == "demo"))
        from moneymatch_api.routers.demo import _ensure_demo_fixture

        await _ensure_demo_fixture(session, user)

        wallet = await wallet_service.get_wallet(session, user.id)
        before = wallet.available_cents
        line(f"balance before:       ${before / 100:,.2f}")

        # 1. Form a room, exactly as the router does.
        await pool_engine.cancel(session, user)
        await test_opponents.fill_pool(
            session,
            user,
            game=GAME,
            metric=METRIC,
            difficulty=DIFFICULTY,
            entry_cents=ENTRY,
        )
        result = await pool_engine.enqueue(
            session,
            user,
            game=GAME,
            metric=METRIC,
            difficulty=DIFFICULTY,
            entry_cents=ENTRY,
        )
        pool = result.pool
        if pool is None:
            await session.rollback()
            line("no room formed; cannot verify")
            raise SystemExit(1)

        # 2. Inject a clearing result for the real entrant only. Committed
        #    together with the room, because the adapter reads it in a session
        #    of its own.
        link = await linking_service.get_link(session, user.id, GAME)
        clearing = round(float(pool.room_bar) + 0.30, 2)
        await demo_simulation.record(
            session,
            user_id=user.id,
            game=GAME,
            host_account_id=link.host_account_id,
            metrics={METRIC: clearing, "cs2_adr": 95.0, "cs2_headshot_pct": 55.0},
            won=True,
            rounds=22,
            played_at=datetime.now(UTC),
            created_by="verify-escape-hatch",
        )
        await session.commit()

        wallet = await wallet_service.get_wallet(session, user.id)
        line(f"balance after escrow: ${wallet.available_cents / 100:,.2f}")
        line(
            f"room formed:          size={pool.room_size} bar={pool.room_bar} "
            f"pot=${pool.pot_cents / 100:,.2f}"
        )
        line(f"injected:             {METRIC}={clearing} (needs {pool.room_bar})")

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
        line(f"balance after settle: ${after / 100:,.2f}")
        line(f"net:                  ${(after - before) / 100:+,.2f}")

        ok = settled.state == "SETTLED" and after > before
        line("\nPASS: an injected match settled a real wager" if ok else "\nFAIL")
        if not ok:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
