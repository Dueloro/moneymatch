"""Tournament scoring from stored matches, with a reason for every game.

The rules, in the order each game is checked (oldest game first):

1. Started before the tournament opened        → STARTED_BEFORE_START
2. Started before *you* joined                  → STARTED_BEFORE_ENTRY
3. Not a mode that counts (PUBG custom/event, a
   casual chess game, a non-blitz chess game)   → WRONG_MODE
4. Finished after the tournament ended          → ENDED_AFTER_CUTOFF
   (a game still running at the end does not count)
5. Chess only, anti-farming:
   - opponent's Lichess rating is provisional   → OPPONENT_PROVISIONAL
     (every brand-new throwaway account is)
   - you already played this opponent here      → REPEAT_OPPONENT
   Neither uses up one of your counted games.
6. Already have `N` counted games                → OVER_GAME_CAP
7. Chess game under `CHESS_MIN_MOVES_TO_SCORE`  → TOO_SHORT
   It **does** use one of your N games but scores 0, win or draw. So an alt
   resigning on move 2 earns nothing, and resigning early yourself does not
   make a loss disappear.
8. Otherwise                                    → COUNTED

Score:
- chess points: win 1, draw ½, loss 0, summed over counted games;
- every other stat: your **best** counted game (highest value).
No counted game at all → no score (you cannot place).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.stored import norm_from_row
from ..constants import (
    CHESS_MIN_MOVES_TO_SCORE,
    CHESS_TOURNAMENT_SPEED,
    GAME_CHESS_LICHESS,
    rated_only_game,
)
from ..models.game_match import GameMatch
from ..models.tournaments import Tournament, TournamentEntry
from . import aggregate_metrics, test_opponents

CHESS_POINTS = "chess_points"

COUNTED = "COUNTED"
TOO_SHORT = "TOO_SHORT"
WRONG_MODE = "WRONG_MODE"
STARTED_BEFORE_START = "STARTED_BEFORE_START"
STARTED_BEFORE_ENTRY = "STARTED_BEFORE_ENTRY"
ENDED_AFTER_CUTOFF = "ENDED_AFTER_CUTOFF"
OVER_GAME_CAP = "OVER_GAME_CAP"
OPPONENT_PROVISIONAL = "OPPONENT_PROVISIONAL"
REPEAT_OPPONENT = "REPEAT_OPPONENT"
NO_STAT = "NO_STAT"

#: Plain-English reason text for the UI and the admin log.
REASON_TEXT: dict[str, str] = {
    COUNTED: "Counted",
    TOO_SHORT: f"Under {CHESS_MIN_MOVES_TO_SCORE} moves: used a game, scored 0",
    WRONG_MODE: "Mode doesn't count for this tournament",
    STARTED_BEFORE_START: "Started before the tournament",
    STARTED_BEFORE_ENTRY: "Started before you joined",
    ENDED_AFTER_CUTOFF: "Finished after the tournament ended",
    OVER_GAME_CAP: "You already had your counted games",
    OPPONENT_PROVISIONAL: "Opponent's rating is provisional",
    REPEAT_OPPONENT: "Already played this opponent in this tournament",
    NO_STAT: "The stat wasn't recorded for this game",
}

#: Games shown around a tournament: this long before it opens and after it ends.
DISPLAY_MARGIN = timedelta(hours=1)


class StoredGame(Protocol):
    host_match_id: str
    started_at: datetime
    ended_at: datetime | None
    mode: str | None
    rated: bool
    eligible: bool
    result: str | None
    moves: int
    metrics: dict[str, Any]
    detail: dict[str, Any]


@dataclass
class GameVerdict:
    host_match_id: str
    started_at: datetime
    ended_at: datetime | None
    mode: str | None
    result: str | None
    reason: str
    #: What this game contributed: points (chess) or the stat value. None when
    #: it did not count.
    value: float | None = None
    #: Provenance for the settlement log (tournament_log.py): the stored row,
    #: when we fetched it, and the stats it was scored from.
    game_match_id: uuid.UUID | None = None
    fetched_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "host_match_id": self.host_match_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "mode": self.mode,
            "result": self.result,
            "reason": self.reason,
            "reason_text": REASON_TEXT.get(self.reason, self.reason),
            "value": self.value,
        }


@dataclass
class EntryScore:
    score: float | None
    counted: int
    games: list[GameVerdict] = field(default_factory=list)


def _points(result: str | None) -> float:
    return {"win": 1.0, "draw": 0.5}.get(result or "", 0.0)


def score_games(
    games: Sequence[StoredGame],
    *,
    game: str,
    metric: str,
    window_start: datetime,
    window_end: datetime,
    entered_at: datetime,
    max_counted: int,
    rated_only: bool = True,
) -> EntryScore:
    """Apply the tournament rules to one entrant's stored games (pure)."""
    is_chess = game == GAME_CHESS_LICHESS
    chess_points = metric == CHESS_POINTS
    verdicts: list[GameVerdict] = []
    counted_values: list[float] = []
    slots = 0
    opponents: set[str] = set()

    for g in sorted(games, key=lambda x: x.started_at):
        v = GameVerdict(
            g.host_match_id,
            g.started_at,
            g.ended_at,
            g.mode,
            g.result,
            "",
            game_match_id=getattr(g, "id", None),
            fetched_at=getattr(g, "fetched_at", None),
            metrics=dict(g.metrics or {}),
        )
        verdicts.append(v)
        finished = g.ended_at or g.started_at
        detail = g.detail or {}
        if g.started_at < window_start:
            v.reason = STARTED_BEFORE_START
        elif g.started_at < entered_at:
            v.reason = STARTED_BEFORE_ENTRY
        elif (
            not g.eligible
            or (rated_only and not g.rated)
            or (is_chess and g.mode != CHESS_TOURNAMENT_SPEED)
        ):
            v.reason = WRONG_MODE
        elif finished > window_end:
            v.reason = ENDED_AFTER_CUTOFF
        elif is_chess and detail.get("opponent_provisional"):
            v.reason = OPPONENT_PROVISIONAL
        elif is_chess and detail.get("opponent_id") in opponents:
            v.reason = REPEAT_OPPONENT
        elif not chess_points and metric not in (g.metrics or {}):
            v.reason = NO_STAT
        elif slots >= max_counted:
            v.reason = OVER_GAME_CAP
        else:
            slots += 1
            if is_chess and detail.get("opponent_id"):
                opponents.add(detail["opponent_id"])
            if is_chess and (g.moves or 0) < CHESS_MIN_MOVES_TO_SCORE:
                v.reason = TOO_SHORT
                v.value = 0.0
                if chess_points:
                    counted_values.append(0.0)
                continue
            v.reason = COUNTED
            v.value = _points(g.result) if chess_points else float(g.metrics[metric])
            counted_values.append(v.value)

    if slots == 0:
        return EntryScore(score=None, counted=0, games=verdicts)
    score: float | None
    if chess_points:
        score = sum(counted_values)
    else:
        # Only COUNTED games carry a stat; a slot can't be TOO_SHORT off chess.
        score = max(counted_values) if counted_values else None
    return EntryScore(score=score, counted=slots, games=verdicts)


def _legacy_aggregate(
    games: Sequence[StoredGame], metric: str, window_start, window_end, entered_at
) -> EntryScore:
    """Tournaments opened under the retired chess contests (win streak, total
    wins, fastest win) still settle, scored over their in-window rated games."""
    spec = aggregate_metrics.get(metric)
    assert spec is not None
    in_window = [
        g
        for g in games
        if g.eligible
        and g.rated
        and g.started_at >= max(window_start, entered_at)
        and (g.ended_at or g.started_at) <= window_end
    ]
    norms = [norm_from_row(g) for g in in_window]  # type: ignore[arg-type]
    score = spec.score(norms) if norms else None
    return EntryScore(score=score, counted=spec.counted(norms))


async def stored_games_for(
    session: AsyncSession, tournament: Tournament, host_account_id: str
) -> list[GameMatch]:
    """An entrant's stored games from an hour before the tournament to an hour
    after (the extra margin is shown in the log, never counted)."""
    if tournament.window_starts_at is None or tournament.window_ends_at is None:
        return []  # waiting for a second player: no window yet
    return list(
        await session.scalars(
            select(GameMatch)
            .where(
                GameMatch.game == tournament.game,
                GameMatch.host_account_id == host_account_id,
                GameMatch.started_at >= tournament.window_starts_at - DISPLAY_MARGIN,
                GameMatch.started_at <= tournament.window_ends_at + DISPLAY_MARGIN,
            )
            .order_by(GameMatch.started_at.asc())
        )
    )


async def score_entries(
    session: AsyncSession,
    tournament: Tournament,
    entries: list[TournamentEntry],
) -> dict[uuid.UUID, EntryScore]:
    """Score every entrant from stored games (no host calls)."""
    out: dict[uuid.UUID, EntryScore] = {}
    metric = tournament.ranking_metric
    if tournament.window_starts_at is None or tournament.window_ends_at is None:
        # Still waiting for a second player: nothing can count yet.
        return {e.id: EntryScore(score=None, counted=0) for e in entries}
    for entry in entries:
        if test_opponents.is_practice_opponent(entry.host_account_id):
            out[entry.id] = EntryScore(score=None, counted=0)  # demo bot: forfeits
            continue
        games = await stored_games_for(session, tournament, entry.host_account_id)
        if aggregate_metrics.is_aggregate(metric):
            out[entry.id] = _legacy_aggregate(
                games,
                metric,
                tournament.window_starts_at,
                tournament.window_ends_at,
                entry.enqueued_at,
            )
            continue
        # Production rule for every account, demo included: chess counts rated
        # games only; other games use their own eligible flag.
        rated_only = rated_only_game(tournament.game)
        out[entry.id] = score_games(
            games,
            game=tournament.game,
            metric=metric,
            window_start=tournament.window_starts_at,
            window_end=tournament.window_ends_at,
            entered_at=entry.enqueued_at,
            max_counted=tournament.score_matches,
            rated_only=rated_only,
        )
    return out


async def _usernames(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    from ..models.user import User

    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


async def live_standings(session: AsyncSession, tournament: Tournament) -> list[dict]:
    """Current standings rows, each with that player's per-game verdicts."""
    entries = list(
        await session.scalars(
            select(TournamentEntry).where(
                TournamentEntry.tournament_id == tournament.id,
                TournamentEntry.status == "LOCKED",
            )
        )
    )
    names = await _usernames(session, [e.user_id for e in entries])
    scores = await score_entries(session, tournament, entries)
    higher = aggregate_metrics.higher_is_better(tournament.ranking_metric)
    from .tournament_engine import compute_standings

    ranks = {
        e.id: rank
        for e, rank in compute_standings(
            entries,
            {e.id: scores[e.id].score for e in entries},
            higher_is_better=higher,
        )
    }
    return [
        {
            "user_id": str(e.user_id),
            "username": names.get(e.user_id),
            "score": scores[e.id].score,
            "matches": scores[e.id].counted,
            "rank": ranks.get(e.id),
            "games": [g.as_dict() for g in scores[e.id].games],
        }
        for e in entries
    ]
