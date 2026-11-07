"""`/activity` — the unified activity feed. Every number here is server-derived: your
realized net comes from the ledger-backed `payout_cents`, never from anything the
client sent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import metric_label
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..models.live import LiveSnapshot
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from ..schemas.play import ActivityItem, ActivityResponse
from ..services import dispute_service, live_activity_service
from ..services.markets import get as get_market
from ..services.match_states import CANCELED, PUSHED, SETTLED

router = APIRouter(tags=["activity"])

_TERMINAL = {SETTLED, PUSHED, CANCELED}
_DEFAULT_LIMIT = 50


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    user: CurrentUser,
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> ActivityResponse:
    match_rows = list(
        await session.scalars(
            select(Match)
            .join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(MatchPlayer.user_id == user.id)
            .order_by(Match.created_at.desc())
            .limit(limit)
        )
    )
    match_ids = [m.id for m in match_rows]
    seats = (
        list(
            await session.scalars(
                select(MatchPlayer).where(MatchPlayer.match_id.in_(match_ids))
            )
        )
        if match_ids
        else []
    )
    by_match: dict = {}
    for seat in seats:
        by_match.setdefault(seat.match_id, []).append(seat)

    opp_ids = [s.user_id for s in seats if s.user_id != user.id]
    names = {}
    if opp_ids:
        rows = await session.execute(
            select(User.id, User.username).where(User.id.in_(opp_ids))
        )
        names = {uid: uname for uid, uname in rows}

    items: list[ActivityItem] = []
    for match in match_rows:
        seat_pair = by_match.get(match.id, [])
        yours = next((s for s in seat_pair if s.user_id == user.id), None)
        opp = next((s for s in seat_pair if s.user_id != user.id), None)
        if yours is None:
            continue

        net = None
        if match.state in _TERMINAL:
            escrowed = match.entry_cents if yours.confirmed_at is not None else 0
            net = yours.payout_cents - escrowed

        market = get_market(match.game, match.market)
        items.append(
            ActivityItem(
                type="match",
                id=match.id,
                game=match.game,
                market=match.market,
                market_label=market.label if market else match.market,
                kind=market.kind if market else "",
                state=match.state,
                entry_cents=match.entry_cents,
                net_cents=net,
                opponent_username=names.get(opp.user_id) if opp else None,
                your_stat_line=yours.stat_line,
                opponent_stat_line=opp.stat_line if opp else None,
                detail=_match_detail(match, yours, opp, names),
                created_at=match.created_at,
                resolved_at=match.resolved_at,
            )
        )

    await _append_pools(session, user, items, limit)
    await _append_tournaments(session, user, items, limit)
    await _attach_live(session, user, items)
    await _attach_disputes(session, user, items)
    items.sort(key=lambda i: i.created_at, reverse=True)
    return ActivityResponse(items=items[:limit])


def _seat_stats(match: Match, seat: MatchPlayer | None) -> dict | None:
    if seat is None:
        return None
    detail = (match.outcome_detail or {}).get("detail") or {}
    rich = detail.get(str(seat.user_id))
    if isinstance(rich, dict) and rich:
        return rich
    line = seat.stat_line or {}
    return {k: v for k, v in line.items() if k != "game_id"} or None


def _match_detail(
    match: Match,
    yours: MatchPlayer,
    opp: MatchPlayer | None,
    names: dict,
) -> dict:
    return {
        "kind": "match",
        "game": match.game,
        "opponent": names.get(opp.user_id) if opp else None,
        "entry_cents": match.entry_cents,
        "prize_cents": match.prize_cents,
        "host_game_id": match.host_game_id,
        "your_stats": _seat_stats(match, yours),
        "opponent_stats": _seat_stats(match, opp),
    }


async def _attach_disputes(
    session: AsyncSession, user: User, items: list[ActivityItem]
) -> None:
    statuses = await dispute_service.statuses_for_user(session, user.id)
    if not statuses:
        return
    for item in items:
        item.dispute_status = statuses.get((item.type, item.id))


async def _attach_live(
    session: AsyncSession, user: User, items: list[ActivityItem]
) -> None:
    wanted = {
        i.id: i.type
        for i in items
        if i.type in ("pool", "match") and i.state not in _TERMINAL
    }
    if not wanted:
        return
    rows = await session.scalars(
        select(LiveSnapshot).where(LiveSnapshot.ref_id.in_(wanted.keys()))
    )
    snapshots = {row.ref_id: row.data for row in rows}
    for item in items:
        data = snapshots.get(item.id)
        if data is not None and item.type in ("pool", "match"):
            item.live = live_activity_service.view_for(item.type, data, user.id)


async def _append_pools(
    session: AsyncSession, user: User, items: list[ActivityItem], limit: int
) -> None:
    rows = await session.execute(
        select(SoloEntry, SoloPool)
        .join(SoloPool, SoloPool.id == SoloEntry.pool_id)
        .where(SoloEntry.user_id == user.id)
        .order_by(SoloPool.created_at.desc())
        .limit(limit)
    )
    for entry, pool in rows:
        terminal = pool.state in ("SETTLED", "CANCELED")
        net = (entry.payout_cents - pool.entry_cents) if terminal else None
        items.append(
            ActivityItem(
                type="pool",
                id=pool.id,
                game=pool.game,
                market=pool.metric,
                market_label=metric_label(pool.metric),
                kind="pool",
                state=pool.state,
                entry_cents=pool.entry_cents,
                title=f"{metric_label(pool.metric)} · {pool.difficulty.title()} pool",
                net_cents=net,
                opponent_username=None,
                your_stat_line=entry.telemetry,
                opponent_stat_line=None,
                detail={
                    "kind": "pool",
                    "game": pool.game,
                    "difficulty": pool.difficulty,
                    "metric_label": metric_label(pool.metric),
                    "room_bar": round(pool.room_bar, 2),
                    "personal_bar": round(entry.personal_bar, 2),
                    "entry_cents": pool.entry_cents,
                    "prize_cents": pool.prize_cents,
                    "room_size": pool.room_size,
                    "your_stats": entry.telemetry or None,
                },
                created_at=pool.created_at,
                resolved_at=pool.resolved_at,
            )
        )


async def _append_tournaments(
    session: AsyncSession, user: User, items: list[ActivityItem], limit: int
) -> None:
    rows = await session.execute(
        select(TournamentEntry, Tournament)
        .join(Tournament, Tournament.id == TournamentEntry.tournament_id)
        .where(TournamentEntry.user_id == user.id)
        .order_by(Tournament.created_at.desc())
        .limit(limit)
    )
    for entry, tournament in rows:
        terminal = tournament.state in ("SETTLED", "CANCELED")
        net = (entry.payout_cents - tournament.entry_cents) if terminal else None
        rank = f" · #{entry.rank}" if entry.rank else ""
        live = (
            live_activity_service.tournament_view(tournament, entry)
            if not terminal
            else None
        )
        items.append(
            ActivityItem(
                type="tournament",
                id=tournament.id,
                game=tournament.game,
                market=tournament.ranking_metric,
                market_label=metric_label(tournament.ranking_metric),
                kind="tournament",
                state=tournament.state,
                entry_cents=tournament.entry_cents,
                title=f"{metric_label(tournament.ranking_metric)} tournament{rank}",
                net_cents=net,
                opponent_username=None,
                your_stat_line=entry.telemetry,
                opponent_stat_line=None,
                live=live,
                detail={
                    "kind": "tournament",
                    "game": tournament.game,
                    "metric_label": metric_label(tournament.ranking_metric),
                    "entry_cents": tournament.entry_cents,
                    "prize_cents": tournament.prize_cents,
                    "field_size": tournament.field_size,
                    "your_rank": entry.rank,
                    "your_score": round(entry.score, 2)
                    if entry.score is not None
                    else None,
                    "your_stats": entry.telemetry or None,
                },
                created_at=tournament.created_at,
                resolved_at=tournament.resolved_at,
            )
        )
