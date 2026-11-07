"""The verified, host-derived skill profile (the `linked_accounts` snapshot)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Speed = Literal["bullet", "blitz", "rapid", "classical"]

LinkMethod = Literal["username", "oauth"]


class FormatStat(BaseModel):
    """A single chess time-control's verified stats, sourced from the host."""

    speed: Speed
    rating: int
    games: int
    provisional: bool = False


class ProfileSnapshot(BaseModel):
    """Verified skill profile for one linked host account."""

    username: str
    display_name: str
    url: str
    link_method: LinkMethod
    game: str = "chess.lichess"
    account_age_days: int | None = None
    win_rate: float
    draw_rate: float = 0.0
    total_games: int
    formats: list[FormatStat] = []
    primary_speed: Speed | None = None
    rating: int | None = None
    avatar_url: str | None = None
