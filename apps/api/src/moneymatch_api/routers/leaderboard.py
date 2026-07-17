"""`/leaderboard` — real users ranked by ROI over a rolling window (design p.7).

The PoC's seeded bot field is gone; every number is computed server-side from the
ledger (08-phase-5 · deliverable 5). Honest empty state when nobody qualifies yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..schemas.leaderboard import (
    LeaderboardResponse,
    LeaderboardRowView,
    YouSummaryView,
)
from ..services import leaderboard as leaderboard_service
from ..services.leaderboard import LeaderboardRow

router = APIRouter(tags=["leaderboard"])


def _row(row: LeaderboardRow) -> LeaderboardRowView:
    return LeaderboardRowView(
        rank=row.rank,
        user_id=row.user_id,
        username=row.username,
        roi_bps=row.roi_bps,
        net_cents=row.net_cents,
        staked_cents=row.staked_cents,
        contests=row.contests,
        is_you=row.is_you,
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> LeaderboardResponse:
    board = await leaderboard_service.compute(session, user)
    return LeaderboardResponse(
        rows=[_row(r) for r in board.rows],
        you=YouSummaryView(
            qualified=board.you.qualified,
            contests=board.you.contests,
            contests_needed=board.you.contests_needed,
            row=_row(board.you.row) if board.you.row else None,
        ),
        window_days=board.window_days,
        min_contests=board.min_contests,
    )
