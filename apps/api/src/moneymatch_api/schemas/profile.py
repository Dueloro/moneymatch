"""The verified, host-derived skill profile (the `linked_accounts` snapshot).

Ported from the PoC's `SkillProfile` / `FormatStat` (11-migration-map §2). This
is the shape every adapter produces from a host account and that we persist as
`linked_accounts.profile_snapshot` (jsonb) and return from `/links`. It carries
no money and no odds — just verified identity + skill descriptors that drive
bracketing and the Profile screen.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# Lichess time controls we run contests for.
Speed = Literal["bullet", "blitz", "rapid", "classical"]

# How an account was linked. `username` ships at MVP; `oauth` is the next step
# (05-phase-2 · OAuth posture) — the column + this literal reserve the shape.
LinkMethod = Literal["username", "oauth"]


class FormatStat(BaseModel):
    """A single chess time-control's verified stats, sourced from the host."""

    speed: Speed
    rating: int
    games: int
    provisional: bool = False


class ProfileSnapshot(BaseModel):
    """Verified skill profile for one linked host account.

    Chess populates the per-format / `primary_speed` fields; other titles leave
    those empty and use the generic `rating` / `rank_label` / `kd` descriptors.
    `game` is the adapter id.
    """

    username: str
    display_name: str
    url: str
    link_method: LinkMethod
    game: str = "chess.lichess"
    account_age_days: int | None = None
    # Overall record across the user's history (a soft signal for bracketing).
    win_rate: float  # (wins + 0.5*draws) / total, 0..1
    draw_rate: float = 0.0  # draws / total, 0..1 (chess; 0 where N/A)
    total_games: int
    # Chess-specific (empty for other titles).
    formats: list[FormatStat] = []
    primary_speed: Speed | None = None
    # Generic skill descriptors usable by any title.
    rating: int | None = None  # elo / mmr / faceit_elo
    rank_label: str | None = None  # e.g. "Level 10", "Divine"
    kd: float | None = None  # average kill/death ratio (FPS)
    avatar_url: str | None = None
