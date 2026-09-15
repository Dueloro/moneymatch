"""`/tournaments` — matchmade single-metric fields (07-phase-4).

Queue-matched like pools: pick a metric + entry and enqueue; the matcher forms a
field under the μ-dispersion cap. Standings are server-computed (cached during
the window, final at settle). No endpoint accepts a score, rank, or payout.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..constants import (
    ENTRY_PRESETS_CENTS,
    STAT_BASELINE_MIN_N,
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
from ..models.play import QueueTicket
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
from ..services import (
    aggregate_metrics,
    fingerprint_service,
    linking_service,
    test_opponents,
    tournament_engine,
)
from ..services.tournament_engine import TournamentEnqueueResult

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def _device_signals(request: Request, user: User) -> list[str]:
    device_id = request.headers.get("x-device-id")
    ip = request.client.host if request.client else None
    return fingerprint_service.build_signals(device_id=device_id, ip=ip)


async def _guard_co_entry(
    session: AsyncSession, user: User, request: Request, game: str, metric: str
) -> None:
    """Record this client's identity signals and block entry if another account
    queued for the same market shares one (same-human co-entry). Practice
    opponents are exempt (they're all server-made and share no device)."""
    signals = _device_signals(request, user)
    await fingerprint_service.record_signals(session, user.id, signals)
    if test_opponents.is_enabled(user):
        return  # demo/practice path never collides with itself
    # Other accounts currently waiting for the same game+market.
    others = list(
        await session.scalars(
            select(QueueTicket.user_id).where(
                QueueTicket.game == game,
                QueueTicket.market == metric,
                QueueTicket.state == "waiting",
                QueueTicket.user_id != user.id,
            )
        )
    )
    if others and not await fingerprint_service.can_co_enter(session, user.id, others):
        raise APIError(
            "co_entry_blocked",
            "Another account on this device or network is already in this contest.",
            status_code=409,
        )


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
        waited = int((clock.now() - result.ticket.created_at).total_seconds())
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
    # Deterministic ordering (active first, most-recent next) so the readiness
    # shown matches the account settlement actually grades on.
    linked = await linking_service.get_link(session, user.id, game)
    metrics = []
    for metric in TOURNAMENT_METRICS[game]:
        if aggregate_metrics.is_aggregate(metric):
            # Total wins / streak / fastest win are scored straight off the host
            # record over the window, so there is no per-match rate model to
            # gate on. The field forms on the host rating instead, which is what
            # `tournament_engine._build_baseline` requires, so mirror that here.
            provisional = (
                linked is None or tournament_engine.host_rating(linked) is None
            )
        else:
            model = await session.scalar(
                select(MetricModel).where(
                    MetricModel.user_id == user.id,
                    MetricModel.game == game,
                    MetricModel.metric == metric,
                )
            )
            provisional = (model.n if model else 0) < STAT_BASELINE_MIN_N
        metrics.append(
            TournamentMetric(
                metric=metric,
                label=metric_label(metric),
                provisional=provisional,
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
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TournamentStatusResponse:
    # Same-human / collusion guard: record this client's identity signals, then
    # refuse entry if another account currently queued for the same market shares
    # a signal (same device / IP). Unknown signals never match, so a normal player
    # is never blocked; two accounts on one device are.
    await _guard_co_entry(session, user, request, body.game, body.metric)

    result = await tournament_engine.enqueue(
        session,
        user,
        game=body.game,
        metric=body.metric,
        entry_cents=body.entry_preset_cents,
    )

    # --- practice opponents (scaffolding, delete before launch) ------------- #
    # With one real account nothing ever forms, so the whole fetch/grade/settle
    # path is untestable. The demo account fills the bucket and re-polls, so the
    # contest forms on this same request. Real signups never take this branch.
    if test_opponents.is_enabled(user):
        await test_opponents.fill_tournament(
            session,
            user,
            game=body.game,
            metric=body.metric,
            entry_cents=body.entry_preset_cents,
        )
        result = await tournament_engine.poll_status(session, user)
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
