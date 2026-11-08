"""Asks the game's adapter for the result of the brokered game between the two bound
accounts; draw → PUSH, unfinished at the deadline → CANCEL + refund, host outage →
PENDING(host_error) so the worker extends the window.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from ..adapters import registry
from ..models.play import Match, MatchPlayer
from ..services.hosts.errors import HostUnavailable
from .markets import get as get_market

log = structlog.get_logger(__name__)

WIN = "win"
PUSH = "push"
CANCEL = "cancel"
PENDING = "pending"


@dataclass
class GradeOutcome:
    status: str
    winner_user_id: uuid.UUID | None = None
    stat_lines: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    host_error: bool = False
    # The adapter's colour-neutral live view from the same host call, if any.
    live: dict[str, Any] | None = None


def _deadline_passed(match: Match, now: datetime) -> bool:
    return match.window_ends_at is not None and now >= match.window_ends_at


def _ended_at(ms: int | None) -> str | None:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat() if ms else None


async def _grade_brokered(
    match: Match, seats: list[MatchPlayer], now: datetime
) -> GradeOutcome:
    if not match.host_game_id:
        return GradeOutcome(CANCEL, detail={"reason": "no_brokered_game"})
    adapter = registry.get(match.game)
    handles = [s.host_account_id for s in seats]
    result = await adapter.match_result(match.host_game_id, handles)
    live = result.live
    ending = {
        "termination": result.termination,
        "game_ended_at": _ended_at(result.ended_at_ms),
    }
    if result.finished and result.winner is None:
        reason = "game_aborted" if result.termination == "aborted" else "unknown_finish"
        return GradeOutcome(CANCEL, detail={"reason": reason, **ending}, live=live)
    if not result.finished or result.winner is None:
        if _deadline_passed(match, now):
            return GradeOutcome(
                CANCEL, detail={"reason": "game_never_finished"}, live=live
            )
        return GradeOutcome(PENDING, live=live)
    if result.winner == "":
        return GradeOutcome(PUSH, detail={"reason": "draw", **ending}, live=live)
    winner = next(
        (s for s in seats if s.host_account_id.lower() == result.winner.lower()), None
    )
    if winner is None:
        return GradeOutcome(CANCEL, detail={"reason": "winner_not_bound"}, live=live)
    return GradeOutcome(
        WIN,
        winner_user_id=winner.user_id,
        detail={
            "host_game_id": match.host_game_id,
            "winner_handle": result.winner,
            **ending,
        },
        live=live,
    )


async def grade(
    match: Match,
    seats: list[MatchPlayer],
    now: datetime,
) -> GradeOutcome:
    """Resolve a match to a `GradeOutcome`."""
    market = get_market(match.game, match.market)
    if market is None:
        return GradeOutcome(CANCEL, detail={"reason": "unknown_market"})
    try:
        return await _grade_brokered(match, seats, now)
    except HostUnavailable:
        log.warning("grade.host_unavailable", match_id=str(match.id), game=match.game)
        return GradeOutcome(PENDING, host_error=True)
