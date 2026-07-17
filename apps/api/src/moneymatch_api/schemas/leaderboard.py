"""Leaderboard wire types (design PDF p.7): ROI-ranked real users, you-row
highlighted. ROI is basis points (`3120` → +31.2%); all money is integer cents."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class LeaderboardRowView(BaseModel):
    rank: int
    user_id: UUID
    username: str | None
    roi_bps: int
    net_cents: int
    staked_cents: int
    contests: int
    is_you: bool


class YouSummaryView(BaseModel):
    qualified: bool
    contests: int
    contests_needed: int
    row: LeaderboardRowView | None


class LeaderboardResponse(BaseModel):
    rows: list[LeaderboardRowView]
    you: YouSummaryView
    window_days: int
    min_contests: int
