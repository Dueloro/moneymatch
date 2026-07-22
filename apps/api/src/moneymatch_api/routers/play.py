"""`/play` — markets, the DB-backed queue, the match slip, and the waiting list.

Every write is an **intent with ids** (join a market, confirm a match, take a
waiting slot): the server owns the entry cents, the pairing, the timestamps, and
the settlement. There is deliberately **no settle endpoint** — only the worker
settles (00-README §3; 06-phase-3 exit criteria).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import ENTRY_PRESETS_CENTS, METRIC_PROVISIONAL_MIN_N
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer, QueueTicket
from ..models.skill import MetricModel
from ..models.user import User
from ..schemas.play import (
    MarketRow,
    MarketsResponse,
    MatchPlayerView,
    MatchView,
    QueueRequest,
    QueueStatusResponse,
    WaitingResponse,
    WaitingRow,
)
from ..services import matchmaking, money_math
from ..services.markets import (
    KIND_STAT_RACE,
    KIND_WIN_H2H,
    KIND_WIN_NEXT,
    MarketDef,
)
from ..services.markets import for_game as markets_for_game
from ..services.markets import get as get_market
from ..services.match_lifecycle import cancel_pending, confirm, players

router = APIRouter(prefix="/play", tags=["play"])

_CHESS_SPEEDS = ["bullet", "blitz", "rapid", "classical"]


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# View builders.
# --------------------------------------------------------------------------- #


def _resolution_note(market: MarketDef) -> str:
    if market.kind == KIND_WIN_H2H:
        return "Brokered game between you both · draw = push, entries refunded."
    if market.kind == KIND_WIN_NEXT:
        return "Win beats loss · tie = push. Your next finished match after matchup."
    return (
        f"Higher {market.label} wins · equal = push. Graded from your next "
        "finished match; if your opponent never plays, you win by forfeit after "
        "the window plus a short grace period."
    )


async def _usernames(session: AsyncSession, ids: list[UUID]) -> dict[UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


async def _match_view(session: AsyncSession, match: Match, user: User) -> MatchView:
    seats = await players(session, match.id)
    names = await _usernames(session, [s.user_id for s in seats])
    market = get_market(match.game, match.market)

    your_seat: MatchPlayer | None = None
    opp_seat: MatchPlayer | None = None
    views: list[MatchPlayerView] = []
    for seat in seats:
        is_you = seat.user_id == user.id
        if is_you:
            your_seat = seat
        else:
            opp_seat = seat
        views.append(
            MatchPlayerView(
                user_id=seat.user_id,
                username=names.get(seat.user_id),
                rating=seat.rating,
                color=seat.color,
                confirmed=seat.confirmed_at is not None,
                payout_cents=seat.payout_cents,
                stat_line=seat.stat_line,
                is_you=is_you,
            )
        )

    forecast = None
    if market is not None and your_seat is not None and opp_seat is not None:
        forecast = matchmaking.forecast_between(
            market, your_seat.baseline_snapshot, opp_seat.baseline_snapshot
        )

    return MatchView(
        id=match.id,
        game=match.game,
        market=match.market,
        market_label=market.label if market else match.market,
        kind=market.kind if market else "",
        speed=match.speed,
        entry_cents=match.entry_cents,
        pot_cents=match.pot_cents,
        prize_cents=match.prize_cents,
        rake_cents=match.rake_cents,
        multiplier_bps=money_math.h2h_multiplier_bps(match.rake_bps),
        state=match.state,
        brokered=match.brokered,
        host_game_id=match.host_game_id,
        matched_at=match.matched_at,
        window_ends_at=match.window_ends_at,
        players=views,
        you_confirmed=your_seat.confirmed_at is not None if your_seat else False,
        your_play_url=your_seat.play_url if your_seat else None,
        forecast=forecast,
    )


async def _status_view(
    session: AsyncSession, result: matchmaking.EnqueueResult, user: User
) -> QueueStatusResponse:
    if result.status == "matched" and result.match is not None:
        return QueueStatusResponse(
            status="matched", match=await _match_view(session, result.match, user)
        )
    if result.status == "searching" and result.ticket is not None:
        waited = int((_now() - result.ticket.created_at).total_seconds())
        return QueueStatusResponse(
            status="searching",
            waited_seconds=waited,
            tolerance_stage=result.ticket.tolerance_stage,
        )
    return QueueStatusResponse(status="idle", can_cancel=False)


# --------------------------------------------------------------------------- #
# Markets.
# --------------------------------------------------------------------------- #


@router.get("/markets", response_model=MarketsResponse)
async def get_markets(
    user: CurrentUser,
    game: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> MarketsResponse:
    defs = markets_for_game(game)
    if not defs:
        raise APIError("unknown_game", f"No markets for '{game}'.", status_code=404)

    linked = await session.scalar(
        select(func.count())
        .select_from(LinkedAccount)
        .where(
            LinkedAccount.user_id == user.id,
            LinkedAccount.game == game,
            LinkedAccount.status != "unbound",
        )
    )
    now = _now()
    depth_rows = await session.execute(
        select(QueueTicket.market, func.count())
        .where(
            QueueTicket.game == game,
            QueueTicket.state == "waiting",
            QueueTicket.expires_at > now,
        )
        .group_by(QueueTicket.market)
    )
    depths = {market: int(count) for market, count in depth_rows}

    # Which stat metrics is the viewer still provisional on?
    model_rows = await session.execute(
        select(MetricModel.metric, MetricModel.n).where(
            MetricModel.user_id == user.id, MetricModel.game == game
        )
    )
    n_by_metric = {metric: n for metric, n in model_rows}

    rows: list[MarketRow] = []
    for market in defs:
        provisional = False
        if market.kind == KIND_STAT_RACE and market.metric is not None:
            provisional = n_by_metric.get(market.metric, 0) < METRIC_PROVISIONAL_MIN_N
        rows.append(
            MarketRow(
                key=market.key,
                label=market.label,
                kind=market.kind,
                metric=market.metric,
                requires_speed=market.requires_speed,
                speeds=_CHESS_SPEEDS if market.requires_speed else [],
                multiplier_bps=market.multiplier_bps,
                queue_depth=depths.get(market.key, 0),
                provisional=provisional,
                resolution_note=_resolution_note(market),
            )
        )

    return MarketsResponse(
        game=game,
        linked=bool(linked),
        entry_presets_cents=list(ENTRY_PRESETS_CENTS),
        markets=rows,
    )


# --------------------------------------------------------------------------- #
# Queue.
# --------------------------------------------------------------------------- #


@router.post("/queue", response_model=QueueStatusResponse)
async def join_queue(
    body: QueueRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> QueueStatusResponse:
    result = await matchmaking.enqueue(
        session,
        user,
        game=body.game,
        market_key=body.market,
        entry_cents=body.entry_preset_cents,
        speed=body.speed,
    )
    return await _status_view(session, result, user)


@router.get("/queue/status", response_model=QueueStatusResponse)
async def queue_status(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> QueueStatusResponse:
    result = await matchmaking.poll_status(session, user)
    return await _status_view(session, result, user)


@router.delete("/queue", response_model=QueueStatusResponse)
async def leave_queue(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> QueueStatusResponse:
    await matchmaking.cancel(session, user)
    return QueueStatusResponse(status="idle", can_cancel=False)


# --------------------------------------------------------------------------- #
# Matches.
# --------------------------------------------------------------------------- #


async def _load_match(session: AsyncSession, match_id: UUID) -> Match:
    match = await session.scalar(select(Match).where(Match.id == match_id))
    if match is None:
        raise APIError("match_not_found", "No such match.", status_code=404)
    return match


@router.get("/matches/{match_id}", response_model=MatchView)
async def get_match(
    match_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MatchView:
    match = await _load_match(session, match_id)
    seats = await players(session, match.id)
    if not any(s.user_id == user.id for s in seats):
        raise APIError("not_a_player", "You are not in this match.", status_code=403)
    return await _match_view(session, match, user)


@router.post("/matches/{match_id}/confirm", response_model=MatchView)
async def confirm_match(
    match_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MatchView:
    match = await _load_match(session, match_id)
    await confirm(session, match, user)
    return await _match_view(session, match, user)


@router.post("/matches/{match_id}/decline", response_model=MatchView)
async def decline_match(
    match_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MatchView:
    match = await _load_match(session, match_id)
    seats = await players(session, match.id)
    if not any(s.user_id == user.id for s in seats):
        raise APIError("not_a_player", "You are not in this match.", status_code=403)
    await cancel_pending(session, match, reason="declined")
    return await _match_view(session, match, user)


# --------------------------------------------------------------------------- #
# Waiting list ("Waiting to play").
# --------------------------------------------------------------------------- #


@router.get("/waiting", response_model=WaitingResponse)
async def get_waiting(
    user: CurrentUser,
    game: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> WaitingResponse:
    tickets = await matchmaking.list_waiting(session, user, game=game)
    names = await _usernames(session, [t.user_id for t in tickets])
    now = _now()
    rows = []
    for t in tickets:
        market = get_market(t.game, t.market)
        rows.append(
            WaitingRow(
                ticket_id=t.id,
                game=t.game,
                market=t.market,
                market_label=market.label if market else t.market,
                speed=t.speed,
                entry_cents=t.entry_cents,
                username=names.get(t.user_id),
                rating=t.rating,
                waited_seconds=int((now - t.created_at).total_seconds()),
            )
        )
    return WaitingResponse(waiting=rows)


@router.post("/waiting/{ticket_id}/match", response_model=MatchView)
async def take_waiting(
    ticket_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MatchView:
    match = await matchmaking.take_waiting(session, user, ticket_id)
    return await _match_view(session, match, user)
