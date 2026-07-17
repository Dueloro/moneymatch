"""Leaderboard — real users ranked by ROI, computed from the ledger.

Ports the PoC's ROI/ranking spirit (`poc-reference/api/_lib/leaderboard.py`) with
the substrate rewritten (11-migration-map §1): **no seeded bot field** — real
users only, and every number comes from `ledger_entries`, not a client merge.

The math falls straight out of the ledger sign conventions (see `wallet_service`).
Over a rolling window, per user:

- **staked** = −Σ(`escrow_release`.escrow_delta) — every stake actually *consumed*
  into a settled pot. Pushes, cancels, and **friendlies** refund instead of
  releasing, so they never enter staked (friendlies are leaderboard-excluded by
  construction, no special case needed).
- **net** = Σ(`payout`.amount) + Σ(`escrow_release`.escrow_delta) — prizes won
  minus stakes consumed, i.e. realized P&L (the same quantity `lifetime_net`
  tracks all-time, here windowed).
- **ROI** = net / staked. Qualify at ≥ `LEADERBOARD_MIN_CONTESTS` settled
  contests in the window; a big bankroll grinding break-even can't top the board.

Pure read; ranks by ROI desc (net, then username as stable tiebreaks).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import LEADERBOARD_MIN_CONTESTS, LEADERBOARD_WINDOW_DAYS
from ..models.user import User
from ..models.wallet import LedgerEntry, Wallet

_CONTEST_REFS = ("match", "solo_pool", "tournament")
_MAX_ROWS = 100


@dataclass
class LeaderboardRow:
    rank: int
    user_id: uuid.UUID
    username: str | None
    roi_bps: int  # ROI in basis points (3120 = +31.2%)
    net_cents: int
    staked_cents: int
    contests: int
    is_you: bool


@dataclass
class YouSummary:
    qualified: bool
    contests: int
    contests_needed: int  # more settled contests to qualify (0 if qualified)
    row: LeaderboardRow | None  # your ranked row, if you qualify


@dataclass
class Leaderboard:
    rows: list[LeaderboardRow]
    you: YouSummary
    window_days: int
    min_contests: int


def _now() -> datetime:
    return datetime.now(UTC)


async def compute(
    session: AsyncSession, viewer: User, *, now: datetime | None = None
) -> Leaderboard:
    now = now or _now()
    since = now - timedelta(days=LEADERBOARD_WINDOW_DAYS)

    # Windowed contest ledger, one aggregate row per real user.
    released_delta = case(
        (LedgerEntry.entry_type == "escrow_release", LedgerEntry.escrow_delta_cents),
        else_=0,
    )
    payout_amount = case(
        (LedgerEntry.entry_type == "payout", LedgerEntry.amount_cents), else_=0
    )
    release_ref = case(
        (LedgerEntry.entry_type == "escrow_release", LedgerEntry.ref_id), else_=None
    )

    staked = -func.coalesce(func.sum(released_delta), 0)
    net = func.coalesce(func.sum(payout_amount + released_delta), 0)
    contests = func.count(distinct(release_ref))

    stmt = (
        select(
            User.id,
            User.username,
            staked.label("staked"),
            net.label("net"),
            contests.label("contests"),
        )
        .select_from(LedgerEntry)
        .join(Wallet, Wallet.id == LedgerEntry.wallet_id)
        .join(User, User.id == Wallet.user_id)
        .where(
            LedgerEntry.ref_type.in_(_CONTEST_REFS),
            LedgerEntry.created_at >= since,
            User.username.isnot(None),
        )
        .group_by(User.id, User.username)
    )
    rows = list(await session.execute(stmt))

    # Rank the qualified field by ROI (net, then username as stable tiebreaks).
    qualified = [
        r for r in rows if r.contests >= LEADERBOARD_MIN_CONTESTS and r.staked > 0
    ]
    qualified.sort(
        key=lambda r: (
            -(r.net / r.staked),
            -r.net,
            (r.username or "").lower(),
        )
    )

    ranked: list[LeaderboardRow] = []
    you_row: LeaderboardRow | None = None
    for i, r in enumerate(qualified, start=1):
        row = LeaderboardRow(
            rank=i,
            user_id=r.id,
            username=r.username,
            roi_bps=round(r.net / r.staked * 10_000),
            net_cents=int(r.net),
            staked_cents=int(r.staked),
            contests=int(r.contests),
            is_you=r.id == viewer.id,
        )
        if row.is_you:
            you_row = row
        ranked.append(row)

    # Trim to the top N, but always keep the viewer's row visible if they rank.
    top = ranked[:_MAX_ROWS]
    if you_row is not None and you_row not in top:
        top = [*top, you_row]

    viewer_agg = next((r for r in rows if r.id == viewer.id), None)
    viewer_contests = int(viewer_agg.contests) if viewer_agg else 0
    you = YouSummary(
        qualified=you_row is not None,
        contests=viewer_contests,
        contests_needed=max(0, LEADERBOARD_MIN_CONTESTS - viewer_contests),
        row=you_row,
    )
    return Leaderboard(
        rows=top,
        you=you,
        window_days=LEADERBOARD_WINDOW_DAYS,
        min_contests=LEADERBOARD_MIN_CONTESTS,
    )
