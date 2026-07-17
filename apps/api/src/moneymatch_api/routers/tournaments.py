"""`/tournaments` — matchmade single-metric fields (07-phase-4).

Queue-matched like pools: pick a metric + entry and enqueue; the matcher forms a
field under the μ-dispersion cap. Standings are server-computed (cached during
the window, final at settle). No endpoint accepts a score, rank, or payout.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    ENTRY_PRESETS_CENTS,
    METRIC_PROVISIONAL_MIN_N,
    TOURNAMENT_FIELD_SIZE,
    TOURNAMENT_GAMES,
    TOURNAMENT_METRICS,
    TOURNAMENT_PRIZE_SPLIT,
    TOURNAMENT_SCORE_N,
    metric_label,
)
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.skill import MetricModel
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from ..schemas.tournaments import (
    StandingRow,
    TournamentEnterRequest,
    TournamentMarketsResponse,
    TournamentMetric,
    TournamentsListResponse,
    TournamentStatusResponse,
    TournamentView,
)
from ..services import tournament_engine
from ..services.tournament_engine import TournamentEnqueueResult

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def _now() -> datetime:
    return datetime.now(UTC)


async def _usernames(session: AsyncSession, ids: list[UUID]) -> dict[UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


def _standings(
    tournament: Tournament,
    entries: list[TournamentEntry],
    names: dict[UUID, str | None],
    user_id: UUID,
) -> list[StandingRow]:
    if tournament.state == "SETTLED":
        rows = [
            StandingRow(
                user_id=e.user_id,
                username=names.get(e.user_id),
                score=e.score,
                matches=e.matches_counted,
                rank=e.rank,
                is_you=e.user_id == user_id,
                payout_cents=e.payout_cents,
            )
            for e in entries
        ]
        rows.sort(key=lambda r: (r.rank is None, r.rank or 0))
        return rows

    # In-window: server-computed cache (may be empty until the first refresh).
    cache = {
        r["user_id"]: r for r in ((tournament.standings_cache or {}).get("rows") or [])
    }
    rows = []
    for e in entries:
        c = cache.get(str(e.user_id), {})
        rows.append(
            StandingRow(
                user_id=e.user_id,
                username=names.get(e.user_id),
                score=c.get("score"),
                matches=c.get("matches", 0),
                rank=c.get("rank"),
                is_you=e.user_id == user_id,
                payout_cents=0,
            )
        )
    rows.sort(key=lambda r: (r.score is None, -(r.score or 0.0)))
    return rows


async def _view(
    session: AsyncSession, tournament: Tournament, user: User
) -> TournamentView:
    entries = list(
        await session.scalars(
            select(TournamentEntry).where(
                TournamentEntry.tournament_id == tournament.id
            )
        )
    )
    names = await _usernames(session, [e.user_id for e in entries])
    mus = [
        float(e.baseline_snapshot["mu"])
        for e in entries
        if e.baseline_snapshot and "mu" in e.baseline_snapshot
    ]
    standings = _standings(tournament, entries, names, user.id)
    your = next((e for e in entries if e.user_id == user.id), None)
    return TournamentView(
        id=tournament.id,
        game=tournament.game,
        metric=tournament.ranking_metric,
        metric_label=metric_label(tournament.ranking_metric),
        entry_cents=tournament.entry_cents,
        pot_cents=tournament.pot_cents,
        prize_cents=tournament.prize_cents,
        rake_cents=tournament.rake_cents,
        prize_split=list(tournament.prize_split),
        field_size=tournament.field_size,
        score_matches=tournament.score_matches,
        state=tournament.state,
        window_starts_at=tournament.window_starts_at,
        window_ends_at=tournament.window_ends_at,
        field_mu_low=round(min(mus), 2) if mus else None,
        field_mu_high=round(max(mus), 2) if mus else None,
        standings=standings,
        your_rank=your.rank if your else None,
        your_payout_cents=your.payout_cents if your else None,
        resolved_at=tournament.resolved_at,
    )


async def _status_view(
    session: AsyncSession, result: TournamentEnqueueResult, user: User
) -> TournamentStatusResponse:
    if result.status == "formed" and result.tournament is not None:
        return TournamentStatusResponse(
            status="formed", tournament=await _view(session, result.tournament, user)
        )
    if result.status == "searching" and result.ticket is not None:
        waited = int((_now() - result.ticket.created_at).total_seconds())
        return TournamentStatusResponse(
            status="searching", metric=result.ticket.market, waited_seconds=waited
        )
    return TournamentStatusResponse(status="idle")


@router.get("/markets", response_model=TournamentMarketsResponse)
async def get_markets(
    user: CurrentUser,
    game: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> TournamentMarketsResponse:
    if game not in TOURNAMENT_GAMES:
        raise APIError(
            "tournament_game_unavailable",
            f"No tournaments for {game}.",
            status_code=404,
        )
    linked = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id, LinkedAccount.game == game
        )
    )
    metrics = []
    for metric in TOURNAMENT_METRICS[game]:
        model = await session.scalar(
            select(MetricModel).where(
                MetricModel.user_id == user.id,
                MetricModel.game == game,
                MetricModel.metric == metric,
            )
        )
        n = model.n if model else 0
        metrics.append(
            TournamentMetric(
                metric=metric,
                label=metric_label(metric),
                provisional=n < METRIC_PROVISIONAL_MIN_N,
            )
        )
    return TournamentMarketsResponse(
        game=game,
        linked=linked is not None,
        entry_presets_cents=list(ENTRY_PRESETS_CENTS),
        prize_split=list(TOURNAMENT_PRIZE_SPLIT),
        field_size=TOURNAMENT_FIELD_SIZE,
        score_matches=TOURNAMENT_SCORE_N,
        metrics=metrics,
    )


@router.post("/queue", response_model=TournamentStatusResponse)
async def enter(
    body: TournamentEnterRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> TournamentStatusResponse:
    result = await tournament_engine.enqueue(
        session,
        user,
        game=body.game,
        metric=body.metric,
        entry_cents=body.entry_preset_cents,
    )
    return await _status_view(session, result, user)


@router.get("/queue/status", response_model=TournamentStatusResponse)
async def queue_status(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TournamentStatusResponse:
    result = await tournament_engine.poll_status(session, user)
    return await _status_view(session, result, user)


@router.delete("/queue", response_model=TournamentStatusResponse)
async def leave_queue(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TournamentStatusResponse:
    await tournament_engine.cancel(session, user)
    return TournamentStatusResponse(status="idle")


@router.get("", response_model=TournamentsListResponse)
async def list_tournaments(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TournamentsListResponse:
    status = await _status_view(
        session, await tournament_engine.poll_status(session, user), user
    )
    rows = list(
        await session.scalars(
            select(Tournament)
            .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
            .where(TournamentEntry.user_id == user.id)
            .order_by(Tournament.created_at.desc())
            .limit(20)
        )
    )
    return TournamentsListResponse(
        status=status, tournaments=[await _view(session, t, user) for t in rows]
    )


@router.get("/{tournament_id}", response_model=TournamentView)
async def get_tournament(
    tournament_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> TournamentView:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise APIError("tournament_not_found", "No such tournament.", status_code=404)
    entry = await session.scalar(
        select(TournamentEntry).where(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.user_id == user.id,
        )
    )
    if entry is None:
        raise APIError(
            "not_a_member", "You are not in this tournament.", status_code=403
        )
    return await _view(session, tournament, user)
