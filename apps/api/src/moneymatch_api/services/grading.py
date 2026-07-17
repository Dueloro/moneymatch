"""Result grading — the server-authoritative "who won" (zero self-reporting).

Given an ACTIVE match, this asks the game's adapter what actually happened and
produces a `GradeOutcome`. It never trusts a client: every input comes from a
host API through an adapter, and the normalized evidence is what gets persisted
to `raw_payloads` and referenced from the settlement.

Per market (01-architecture §3.1):
- `win_h2h` (chess): the brokered game's result between the two bound accounts
  (`adapter.match_winner`); draw → PUSH.
- `win_next` (CS2/Dota): each player's first finished match after `matched_at`;
  win beats loss; both-win / both-lose → PUSH.
- stat races: each player's rate stat from that first finished match; higher
  wins; equal → PUSH; both stat lines are stored for the Activity UI.

Watchdog rules (01-architecture §3.4): a host outage returns `pending`
(host_error) so the worker extends the window instead of consuming it; a
one-sided stat duel becomes a **forfeit win** only after the full window plus a
disclosed grace period; nothing resolvable at the deadline → CANCEL + refund.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..constants import (
    FORFEIT_GRACE_SECONDS,
    GRADE_MATCH_SKEW_MS,
)
from ..models.play import Match, MatchPlayer
from ..services.hosts.errors import HostUnavailable
from .markets import KIND_STAT_RACE, KIND_WIN_H2H, KIND_WIN_NEXT, MarketDef
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


@dataclass
class _PlayerResult:
    """One seat's qualifying-match result, or the absence of one."""

    found: bool
    won: bool = False
    stat: float | None = None
    game_id: str | None = None


def _matched_ms(match: Match) -> int:
    assert match.matched_at is not None
    return int(match.matched_at.timestamp() * 1000)


def _first_qualifying_game(games: list[NormGame], matched_ms: int) -> NormGame | None:
    """The earliest finished game at/after `matched_at` (games arrive oldest-first)."""
    cutoff = matched_ms - GRADE_MATCH_SKEW_MS
    for game in games:
        if game.created_at_ms >= cutoff:
            return game
    return None


async def _player_result(
    match: Match, market: MarketDef, seat: MatchPlayer
) -> _PlayerResult:
    """Fetch this seat's first qualifying match after `matched_at` (win + stat)."""
    adapter = registry.get(match.game)
    games = await adapter.poll_eligible_games(
        seat.host_account_id, _matched_ms(match), GameFilters(rated_only=False)
    )
    game = _first_qualifying_game(games, _matched_ms(match))
    if game is None:
        return _PlayerResult(found=False)
    stat: float | None = None
    if market.kind == KIND_STAT_RACE and market.metric is not None:
        stat = game.metrics.get(market.metric)
        if stat is None:
            # Match played but the graded stat wasn't readable → not a result yet.
            return _PlayerResult(found=False, game_id=game.id)
    return _PlayerResult(found=True, won=game.won is True, stat=stat, game_id=game.id)


def _deadline_passed(match: Match, now: datetime) -> bool:
    return match.window_ends_at is not None and now >= match.window_ends_at


def _grace_passed(match: Match, now: datetime) -> bool:
    if match.window_ends_at is None:
        return False
    return now >= match.window_ends_at + timedelta(seconds=FORFEIT_GRACE_SECONDS)


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


async def _grade_coordinated(
    match: Match, market: MarketDef, seats: list[MatchPlayer], now: datetime
) -> GradeOutcome:
    """CS2/Dota: grade each seat's first finished match after `matched_at`."""
    a, b = seats
    ra = await _player_result(match, market, a)
    rb = await _player_result(match, market, b)

    stat_lines: dict[uuid.UUID, dict[str, Any]] = {}
    if market.kind == KIND_STAT_RACE and market.metric is not None:
        if ra.found:
            stat_lines[a.user_id] = {market.metric: ra.stat, "game_id": ra.game_id}
        if rb.found:
            stat_lines[b.user_id] = {market.metric: rb.stat, "game_id": rb.game_id}

    if ra.found and rb.found:
        return _decide(market, a, ra, b, rb, stat_lines)

    # Exactly one played → forfeit win, but only after window + grace.
    if ra.found or rb.found:
        if _grace_passed(match, now):
            winner = a if ra.found else b
            return GradeOutcome(
                WIN,
                winner_user_id=winner.user_id,
                stat_lines=stat_lines,
                detail={"reason": "forfeit"},
            )
        return GradeOutcome(PENDING, stat_lines=stat_lines)

    # Neither played.
    if _deadline_passed(match, now):
        return GradeOutcome(CANCEL, detail={"reason": "no_qualifying_game"})
    return GradeOutcome(PENDING)


def _decide(
    market: MarketDef,
    a: MatchPlayer,
    ra: _PlayerResult,
    b: MatchPlayer,
    rb: _PlayerResult,
    stat_lines: dict[uuid.UUID, dict[str, Any]],
) -> GradeOutcome:
    """Both seats produced a result → decide win/push per the market kind."""
    if market.kind == KIND_STAT_RACE:
        if ra.stat == rb.stat:
            return GradeOutcome(
                PUSH, stat_lines=stat_lines, detail={"reason": "equal_stat"}
            )
        winner = a if (ra.stat or 0) > (rb.stat or 0) else b
        return GradeOutcome(WIN, winner_user_id=winner.user_id, stat_lines=stat_lines)
    # win_next: win beats loss; both-win / both-lose → push.
    if ra.won == rb.won:
        return GradeOutcome(PUSH, detail={"reason": "both_same_result"})
    winner = a if ra.won else b
    return GradeOutcome(WIN, winner_user_id=winner.user_id)


async def grade(match: Match, seats: list[MatchPlayer], now: datetime) -> GradeOutcome:
    """Resolve a match to a `GradeOutcome`. Host outage → PENDING(host_error)."""
    market = get_market(match.game, match.market)
    if market is None:
        return GradeOutcome(CANCEL, detail={"reason": "unknown_market"})
    try:
        if market.kind == KIND_WIN_H2H:
            return await _grade_brokered(match, seats, now)
        if market.kind in (KIND_WIN_NEXT, KIND_STAT_RACE):
            return await _grade_coordinated(match, market, seats, now)
    except HostUnavailable:
        log.warning("grade.host_unavailable", match_id=str(match.id), game=match.game)
        return GradeOutcome(PENDING, host_error=True)
    return GradeOutcome(CANCEL, detail={"reason": "ungradeable_market"})
