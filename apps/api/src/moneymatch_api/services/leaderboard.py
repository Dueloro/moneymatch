"""Leaderboard — real users ranked by ROI, computed from the ledger."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
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
    roi_bps: int
    net_cents: int
    staked_cents: int
    contests: int
    is_you: bool


@dataclass
class YouSummary:
    qualified: bool
    contests: int
    contests_needed: int
    row: LeaderboardRow | None


@dataclass
class Leaderboard:
    rows: list[LeaderboardRow]
    you: YouSummary
    window_days: int
    min_contests: int


async def compute(
    session: AsyncSession, viewer: User, *, now: datetime | None = None
) -> Leaderboard:
    now = now or clock.now()
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
