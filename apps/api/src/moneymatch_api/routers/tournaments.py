"""`/tournaments` — rolling stat tournaments.

Pick a stat tournament (game + stat + entry) and you are in: you join the one
that is open for that choice, or open a new one. Standings and per-game verdicts
are computed on the server from stored matches. No endpoint accepts a score,
rank, or payout.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    CHESS_MIN_MOVES_TO_SCORE,
    CHESS_TOURNAMENT_SPEED,
    ENTRY_PRESETS_CENTS,
    TOURNAMENT_FIELD_SIZE,
    TOURNAMENT_GAMES,
    TOURNAMENT_METRICS,
    TOURNAMENT_MIN_FIELD,
    TOURNAMENT_PRIZE_SPLIT,
    TOURNAMENT_SCORE_N,
    metric_label,
)
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from ..schemas.tournaments import (
    OpenTable,
    StandingRow,
    TournamentEnterRequest,
    TournamentGame,
    TournamentMarketsResponse,
    TournamentMetric,
    TournamentsListResponse,
    TournamentStatusResponse,
    TournamentView,
)
from ..services import (
    demo_mode,
    linking_service,
    test_opponents,
    tournament_engine,
    tournament_scoring,
    tournament_timing,
)
from ..services.tournament_engine import TournamentEnqueueResult

router = APIRouter(prefix="/tournaments", tags=["tournaments"])

_LIVE = ("OPEN", "LOCKED")


def rules_for(game: str, metric: str) -> str:
    """The card's one-line rules, in plain words."""
    n = TOURNAMENT_SCORE_N
    if metric == tournament_scoring.CHESS_POINTS:
        return (
            f"Points from your first {n} rated {CHESS_TOURNAMENT_SPEED} games after "
            f"you join: win 1, draw ½. Games under {CHESS_MIN_MOVES_TO_SCORE} moves "
            "score 0. Games against provisional or repeat opponents don't count."
        )
    return (
        f"Your best {metric_label(metric)} from your first {n} ranked or official "
        "matches after you join, finished before the tournament ends."
    )


async def _usernames(session: AsyncSession, ids: list[UUID]) -> dict[UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


def _games(raw: list[dict] | None) -> list[TournamentGame]:
    out = []
    for g in raw or []:
        out.append(
            TournamentGame(
                host_match_id=g["host_match_id"],
                started_at=datetime.fromisoformat(g["started_at"]),
                ended_at=(
                    datetime.fromisoformat(g["ended_at"]) if g.get("ended_at") else None
                ),
                mode=g.get("mode"),
                result=g.get("result"),
                reason=g["reason"],
                reason_text=g.get("reason_text") or g["reason"],
                value=g.get("value"),
            )
        )
    return out


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
    live_state = tournament.state in _LIVE
    names = await _usernames(session, [e.user_id for e in entries])
    your = next((e for e in entries if e.user_id == user.id), None)
    your_games: list[TournamentGame] = []

    if live_state:
        # Computed per request from stored games: a few indexed reads, no host
        # calls, and never staler than the last ingestion poll.
        live = await tournament_scoring.live_standings(session, tournament)
        standings = [
            StandingRow(
                user_id=UUID(r["user_id"]),
                username=r["username"],
                score=r["score"],
                matches=r["matches"],
                rank=r["rank"],
                is_you=r["user_id"] == str(user.id),
                payout_cents=0,
            )
            for r in live
        ]
        mine = next((r for r in live if r["user_id"] == str(user.id)), None)
        your_games = _games(mine["games"] if mine else None)
        standings.sort(key=lambda r: (r.rank is None, r.rank or 0))
    else:
        standings = [
            StandingRow(
                user_id=e.user_id,
                username=names.get(e.user_id),
                score=e.score,
                matches=e.matches_counted,
                rank=e.rank,
                is_you=e.user_id == user.id,
                payout_cents=e.payout_cents,
            )
            for e in entries
        ]
        standings.sort(key=lambda r: (r.rank is None, r.rank or 0))
        if your is not None:
            your_games = _games((your.telemetry or {}).get("games"))

    mus = [
        float(e.baseline_snapshot["mu"])
        for e in entries
        if e.baseline_snapshot and "mu" in e.baseline_snapshot
    ]
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
        # While running: players still in (someone who left is refunded).
        players=(
            sum(1 for e in entries if e.status != "REFUNDED")
            if live_state
            else len(entries)
        ),
        score_matches=tournament.score_matches,
        state=tournament.state,
        window_starts_at=tournament.window_starts_at,
        window_ends_at=tournament.window_ends_at,
        join_closes_at=tournament.join_closes_at,
        your_entered_at=your.enqueued_at if your else None,
        field_mu_low=round(min(mus), 2) if mus else None,
        field_mu_high=round(max(mus), 2) if mus else None,
        standings=standings,
        your_rank=your.rank if your else None,
        your_payout_cents=your.payout_cents if your else None,
        your_games=your_games,
        outcome_reason=(tournament.outcome_detail or {}).get("reason"),
        resolved_at=tournament.resolved_at,
    )


async def _status_view(
    session: AsyncSession, result: TournamentEnqueueResult, user: User
) -> TournamentStatusResponse:
    if result.status == "formed" and result.tournament is not None:
        return TournamentStatusResponse(
            status="formed", tournament=await _view(session, result.tournament, user)
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
    linked = await linking_service.get_link(session, user.id, game)
    counts = await tournament_engine.open_counts(session, game)
    metrics = [
        TournamentMetric(
            metric=metric,
            label=metric_label(metric),
            provisional=False,
            rules=rules_for(game, metric),
            open_tables=[
                OpenTable(entry_cents=e, players=counts.get((metric, e), 0))
                for e in ENTRY_PRESETS_CENTS
            ],
        )
        for metric in TOURNAMENT_METRICS[game]
    ]
    return TournamentMarketsResponse(
        game=game,
        linked=linked is not None,
        entry_presets_cents=list(ENTRY_PRESETS_CENTS),
        prize_split=list(TOURNAMENT_PRIZE_SPLIT),
        field_size=TOURNAMENT_FIELD_SIZE,
        min_players=TOURNAMENT_MIN_FIELD,
        score_matches=TOURNAMENT_SCORE_N,
        join_window_seconds=tournament_timing.join_window_seconds(),
        duration_seconds=tournament_timing.duration_seconds(),
        metrics=metrics,
    )


@router.post("/queue", response_model=TournamentStatusResponse)
async def enter(
    body: TournamentEnterRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> TournamentStatusResponse:
    """Join the open tournament for this stat + entry (or open one)."""
    if demo_mode.is_demo_user(user):
        # The demo scores from real games, so it needs a real account first.
        link = await linking_service.get_link(session, user.id, body.game)
        if link is not None and demo_mode.is_placeholder_link(
            body.game, link.host_account_id
        ):
            raise APIError(
                "demo_needs_real_account",
                "The demo is still on its placeholder name for this game. Set "
                "your real in-game name under Profile -> Demo handles, then join.",
                status_code=409,
            )
    result = await tournament_engine.enqueue(
        session,
        user,
        game=body.game,
        metric=body.metric,
        entry_cents=body.entry_preset_cents,
    )
    # --- practice opponents (scaffolding, delete before launch) ------------- #
    # Demo account only: bots fill the rest of the field so the demo plays a
    # full tournament alone. They never play, so they finish last and the demo
    # is paid from their entries. The engine keeps demo tournaments apart from
    # real ones, so a real signup never meets a bot.
    if test_opponents.is_enabled(user) and result.tournament is not None:
        missing = result.tournament.field_size - await tournament_engine.active_count(
            session, result.tournament.id
        )
        if missing > 0:
            await test_opponents.fill_tournament(
                session,
                user,
                game=body.game,
                metric=body.metric,
                entry_cents=body.entry_preset_cents,
                count=missing,
            )
    return await _status_view(session, result, user)


@router.get("/queue/status", response_model=TournamentStatusResponse)
async def queue_status(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TournamentStatusResponse:
    result = await tournament_engine.poll_status(session, user)
    return await _status_view(session, result, user)


@router.delete("/queue", response_model=TournamentStatusResponse)
async def leave(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> TournamentStatusResponse:
    """Leave — only while you are still the only player (full refund)."""
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
