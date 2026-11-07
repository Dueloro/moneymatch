"""Result grading: the server-authoritative "who won" (zero self-reporting).

Asks the game's adapter for the result of the brokered game between the two
bound accounts; draw → PUSH, unfinished at the deadline → CANCEL + refund, host
outage → PENDING(host_error) so the worker extends the window.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from ..adapters import registry
from ..models.play import Match, MatchPlayer
from ..services.hosts.errors import HostUnavailable
from .markets import get as get_market

log = structlog.get_logger(__name__)

# Grade statuses.
WIN = "win"
PUSH = "push"
CANCEL = "cancel"
PENDING = "pending"


@dataclass
class GradeOutcome:
    status: str  # WIN | PUSH | CANCEL | PENDING
    winner_user_id: uuid.UUID | None = None
    stat_lines: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    # PENDING only: a host outage caused it (worker extends the window, doesn't
    # consume it). Absent ⇒ simply still waiting for a qualifying game.
    host_error: bool = False


def _deadline_passed(match: Match, now: datetime) -> bool:
    return match.window_ends_at is not None and now >= match.window_ends_at


async def _grade_brokered(
    match: Match, seats: list[MatchPlayer], now: datetime
) -> GradeOutcome:
    """Chess `win_h2h`: grade the specific brokered game between the two accounts."""
    if not match.host_game_id:
        return GradeOutcome(CANCEL, detail={"reason": "no_brokered_game"})
    adapter = registry.get(match.game)
    handles = [s.host_account_id for s in seats]
    winner_handle = await adapter.match_winner(match.host_game_id, handles)
    if winner_handle is None:  # unfinished / unverifiable
        if _deadline_passed(match, now):
            return GradeOutcome(CANCEL, detail={"reason": "game_never_finished"})
        return GradeOutcome(PENDING)
    if winner_handle == "":  # draw
        return GradeOutcome(PUSH, detail={"reason": "draw"})
    winner = next(
        (s for s in seats if s.host_account_id.lower() == winner_handle.lower()), None
    )
    if winner is None:
        return GradeOutcome(CANCEL, detail={"reason": "winner_not_bound"})
    return GradeOutcome(
        WIN,
        winner_user_id=winner.user_id,
        detail={"host_game_id": match.host_game_id, "winner_handle": winner_handle},
    )


async def grade(
    match: Match,
    seats: list[MatchPlayer],
    now: datetime,
) -> GradeOutcome:
    """Resolve a match to a `GradeOutcome`. Host outage → PENDING(host_error)."""
    market = get_market(match.game, match.market)
    if market is None:
        return GradeOutcome(CANCEL, detail={"reason": "unknown_market"})
    try:
        return await _grade_brokered(match, seats, now)
    except HostUnavailable:
        log.warning("grade.host_unavailable", match_id=str(match.id), game=match.game)
        return GradeOutcome(PENDING, host_error=True)
