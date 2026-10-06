"""Write the permanent settlement log for a finished tournament.

Called once, right after `tournament_engine.settle_tournament` has ranked, paid
or refunded the field, in the same transaction, so the log always matches the
money. See `models/tournament_log.py` for what is kept and why.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tournament_log import TournamentMatchLog, TournamentResult
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from . import test_opponents
from .tournament_scoring import COUNTED, EntryScore

log = structlog.get_logger(__name__)


def _outcome(entry: TournamentEntry, unverifiable: set[uuid.UUID]) -> str:
    if test_opponents.is_practice_opponent(entry.host_account_id):
        return "forfeit"
    if entry.id in unverifiable:
        return "unverifiable"
    if entry.status == "REFUNDED":
        return "refunded"
    return "paid" if (entry.payout_cents or 0) > 0 else "unpaid"


async def record(
    session: AsyncSession,
    tournament: Tournament,
    entries: list[TournamentEntry],
    scores: dict[uuid.UUID, EntryScore],
    unverifiable: set[uuid.UUID],
) -> int:
    """Insert one result row per entrant and one log row per fetched match.
    Idempotent (unique keys, ON CONFLICT DO NOTHING). Returns match rows written."""
    rows = await session.execute(
        select(User.id, User.username).where(User.id.in_([e.user_id for e in entries]))
    )
    names: dict[uuid.UUID, str | None] = {uid: name for uid, name in rows}
    reason = (tournament.outcome_detail or {}).get("reason")
    reason = str(reason)[:48] if reason else None  # admin voids carry free text
    written = 0
    for e in entries:
        sc = scores.get(e.id) or EntryScore(score=None, counted=0)
        await session.execute(
            insert(TournamentResult)
            .values(
                tournament_id=tournament.id,
                entry_id=e.id,
                user_id=e.user_id,
                username=names.get(e.user_id),
                host_account_id=e.host_account_id,
                entered_at=e.enqueued_at,
                score=sc.score,
                matches_counted=sc.counted,
                rank=e.rank,
                entry_cents=tournament.entry_cents,
                payout_cents=e.payout_cents or 0,
                outcome=_outcome(e, unverifiable),
                tournament_outcome=reason,
            )
            .on_conflict_do_nothing(constraint="uq_tournament_results_entry")
        )
        for g in sc.games:
            await session.execute(
                insert(TournamentMatchLog)
                .values(
                    tournament_id=tournament.id,
                    entry_id=e.id,
                    user_id=e.user_id,
                    game_match_id=g.game_match_id,
                    host_account_id=e.host_account_id,
                    host_match_id=g.host_match_id,
                    started_at=g.started_at,
                    ended_at=g.ended_at,
                    fetched_at=g.fetched_at,
                    mode=g.mode,
                    result=g.result,
                    reason=g.reason,
                    counted=g.reason == COUNTED,
                    value=g.value,
                    metrics=g.metrics,
                )
                .on_conflict_do_nothing(
                    constraint="uq_tournament_match_log_entry_match"
                )
            )
            written += 1
    await session.flush()
    log.info(
        "tournament.log_recorded",
        tournament_id=str(tournament.id),
        entrants=len(entries),
        matches=written,
    )
    return written
