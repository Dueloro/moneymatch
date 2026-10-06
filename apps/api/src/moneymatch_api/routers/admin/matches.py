"""`/admin/game-matches` and `/admin/tournaments/{id}/void`.

- The match log: every game the background ingester has fetched and stored,
  newest first, filterable by player and game, so an operator can see exactly
  what a tournament was scored from.
- Void a tournament: refund every entrant, no rake. Requires a written reason
  and is audited.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...errors import APIError
from ...models.game_match import GameMatch
from ...models.linked_account import LinkedAccount
from ...models.tournament_log import TournamentMatchLog, TournamentResult
from ...models.tournaments import Tournament, TournamentEntry
from ...models.user import User
from ...schemas.admin import (
    AdminGameMatch,
    AdminGameMatchesResponse,
    AdminTournamentLogEntrant,
    AdminTournamentLogMatch,
    AdminTournamentLogResponse,
    ResettleResult,
    VoidRequest,
)
from ...services import (
    admin_audit_service,
    tournament_engine,
    tournament_log,
    tournament_scoring,
)
from ...services.tournament_scoring import REASON_TEXT

router = APIRouter(tags=["admin"])


@router.get("/game-matches", response_model=AdminGameMatchesResponse)
async def list_game_matches(
    _admin: AdminUser,
    player: str | None = Query(
        default=None, description="Username, or the host account id / handle"
    ),
    game: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> AdminGameMatchesResponse:
    stmt = (
        select(GameMatch, User.username, LinkedAccount.host_username)
        .join(User, User.id == GameMatch.user_id)
        .join(LinkedAccount, LinkedAccount.id == GameMatch.linked_account_id)
        .order_by(GameMatch.started_at.desc())
        .limit(limit)
    )
    if game:
        stmt = stmt.where(GameMatch.game == game)
    if player:
        needle = player.strip()
        stmt = stmt.where(
            or_(
                User.username.ilike(needle),
                GameMatch.host_account_id == needle.casefold(),
                LinkedAccount.host_username.ilike(needle),
            )
        )
    rows = (await session.execute(stmt)).all()

    # Per-account polling status, so "why is nothing here" is answerable.
    link_ids = {gm.linked_account_id for gm, _, _ in rows}
    polled: dict[UUID, datetime | None] = {}
    if link_ids:
        result = await session.execute(
            select(LinkedAccount.id, LinkedAccount.ingest_polled_at).where(
                LinkedAccount.id.in_(link_ids)
            )
        )
        polled = {lid: at for lid, at in result.all()}
    return AdminGameMatchesResponse(
        matches=[
            AdminGameMatch(
                id=gm.id,
                user_id=gm.user_id,
                username=username,
                host_username=host_username,
                game=gm.game,
                host_account_id=gm.host_account_id,
                host_match_id=gm.host_match_id,
                started_at=gm.started_at,
                ended_at=gm.ended_at,
                mode=gm.mode,
                rated=gm.rated,
                eligible=gm.eligible,
                result=gm.result,
                moves=gm.moves,
                metrics=gm.metrics or {},
                detail=gm.detail or {},
                fetched_at=gm.fetched_at,
                account_last_polled_at=polled.get(gm.linked_account_id),
            )
            for gm, username, host_username in rows
        ]
    )


@router.get(
    "/tournaments/{tournament_id}/log", response_model=AdminTournamentLogResponse
)
async def tournament_log_view(
    tournament_id: UUID,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> AdminTournamentLogResponse:
    """The permanent settlement log: every entrant's result and every match of
    theirs we had, with the verdict and timestamps. Empty until it finishes."""
    if await session.get(Tournament, tournament_id) is None:
        raise APIError("contest_not_found", "No such tournament.", status_code=404)
    results = list(
        await session.scalars(
            select(TournamentResult)
            .where(TournamentResult.tournament_id == tournament_id)
            .order_by(
                TournamentResult.rank.asc().nulls_last(), TournamentResult.username
            )
        )
    )
    rows = list(
        await session.scalars(
            select(TournamentMatchLog)
            .where(TournamentMatchLog.tournament_id == tournament_id)
            .order_by(TournamentMatchLog.started_at.asc())
        )
    )
    by_entry: dict[UUID, list[AdminTournamentLogMatch]] = {}
    for m in rows:
        by_entry.setdefault(m.entry_id, []).append(
            AdminTournamentLogMatch(
                host_match_id=m.host_match_id,
                game_match_id=m.game_match_id,
                started_at=m.started_at,
                ended_at=m.ended_at,
                fetched_at=m.fetched_at,
                mode=m.mode,
                result=m.result,
                reason=m.reason,
                reason_text=REASON_TEXT.get(m.reason, m.reason),
                counted=m.counted,
                value=m.value,
                metrics=m.metrics,
                recorded_at=m.recorded_at,
            )
        )
    return AdminTournamentLogResponse(
        tournament_id=tournament_id,
        tournament_outcome=results[0].tournament_outcome if results else None,
        recorded_at=results[0].recorded_at if results else None,
        entrants=[
            AdminTournamentLogEntrant(
                entry_id=r.entry_id,
                user_id=r.user_id,
                username=r.username,
                host_account_id=r.host_account_id,
                entered_at=r.entered_at,
                score=r.score,
                matches_counted=r.matches_counted,
                rank=r.rank,
                entry_cents=r.entry_cents,
                payout_cents=r.payout_cents,
                outcome=r.outcome,
                matches=by_entry.get(r.entry_id, []),
            )
            for r in results
        ],
    )


@router.post("/tournaments/{tournament_id}/void", response_model=ResettleResult)
async def void_tournament(
    tournament_id: UUID,
    body: VoidRequest,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ResettleResult:
    tournament = await session.scalar(
        select(Tournament).where(Tournament.id == tournament_id).with_for_update()
    )
    if tournament is None:
        raise APIError("contest_not_found", "No such tournament.", status_code=404)
    if tournament.state in ("SETTLED", "CANCELED"):
        raise APIError(
            "already_terminal",
            "This tournament is already finished.",
            status_code=409,
        )
    # Keep the same permanent record a settlement writes: who was in, and
    # every game of theirs we had, as scored at the moment of the void.
    entries = list(
        await session.scalars(
            select(TournamentEntry).where(
                TournamentEntry.tournament_id == tournament.id,
                TournamentEntry.status == "LOCKED",
            )
        )
    )
    scores = await tournament_scoring.score_entries(session, tournament, entries)
    await tournament_engine.cancel_tournament(
        session, tournament, reason=f"admin: {body.reason}"
    )
    await tournament_log.record(session, tournament, entries, scores, set())
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="tournament.void",
        target=str(tournament_id),
        detail={"reason": body.reason},
    )
    return ResettleResult(outcome="void", state=tournament.state)
