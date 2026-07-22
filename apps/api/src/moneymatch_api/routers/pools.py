"""`/pools` — queue-matched solo pools (07-phase-4).

Pools are **not** browse-and-join: a player picks metric + difficulty + entry and
enqueues; the matcher forms a fair room. "Open pools" = your in-flight rooms +
your queue state. Entering escrows only at formation (no escrow while waiting).
No endpoint accepts a bar, room bar, or payout — the server owns every number.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    ENTRY_PRESETS_CENTS,
    POOL_GAMES,
    POOL_METRICS,
    metric_label,
)
from ..db.session import get_session
from ..dependencies import CurrentUser
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.pools import SoloEntry, SoloPool
from ..models.user import User
from ..schemas.pools import (
    DifficultyCard,
    PoolEnterRequest,
    PoolMarketsResponse,
    PoolMemberView,
    PoolMetric,
    PoolsListResponse,
    PoolStatusResponse,
    PoolView,
)
from ..services import money_math, pool_engine
from ..services.pool_engine import PoolEnqueueResult

router = APIRouter(prefix="/pools", tags=["pools"])


def _now() -> datetime:
    return datetime.now(UTC)


async def _usernames(session: AsyncSession, ids: list[UUID]) -> dict[UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


async def _pool_view(session: AsyncSession, pool: SoloPool, user: User) -> PoolView:
    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    names = await _usernames(session, [e.user_id for e in entries])
    your = next((e for e in entries if e.user_id == user.id), None)
    members = [
        PoolMemberView(
            user_id=e.user_id,
            username=names.get(e.user_id),
            personal_bar=e.personal_bar,
            status=e.status,
            payout_cents=e.payout_cents,
            is_you=e.user_id == user.id,
        )
        for e in entries
    ]
    your_bar = your.personal_bar if your else None
    return PoolView(
        id=pool.id,
        game=pool.game,
        metric=pool.metric,
        metric_label=metric_label(pool.metric),
        difficulty=pool.difficulty,
        room_bar=pool.room_bar,
        your_bar=your_bar,
        bar_delta=round(pool.room_bar - your_bar, 4) if your_bar is not None else None,
        entry_cents=pool.entry_cents,
        pot_cents=pool.pot_cents,
        prize_cents=pool.prize_cents,
        rake_cents=pool.rake_cents,
        room_size=pool.room_size,
        state=pool.state,
        window_starts_at=pool.window_starts_at,
        window_ends_at=pool.window_ends_at,
        members=members,
        your_payout_cents=your.payout_cents if your else None,
        resolved_at=pool.resolved_at,
    )


async def _status_view(
    session: AsyncSession, result: PoolEnqueueResult, user: User
) -> PoolStatusResponse:
    if result.status == "formed" and result.pool is not None:
        return PoolStatusResponse(
            status="formed", pool=await _pool_view(session, result.pool, user)
        )
    if result.status == "searching" and result.ticket is not None:
        waited = int((_now() - result.ticket.created_at).total_seconds())
        return PoolStatusResponse(
            status="searching",
            difficulty=result.ticket.difficulty,
            metric=result.ticket.market,
            waited_seconds=waited,
        )
    return PoolStatusResponse(status="idle")


@router.get("/markets", response_model=PoolMarketsResponse)
async def get_markets(
    user: CurrentUser,
    game: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> PoolMarketsResponse:
    if game not in POOL_GAMES:
        raise APIError(
            "pool_game_unavailable", f"No pools for {game}.", status_code=404
        )
    linked = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id,
            LinkedAccount.game == game,
            LinkedAccount.status != "unbound",
        )
    )
    metrics: list[PoolMetric] = []
    for metric in POOL_METRICS[game]:
        preview = await pool_engine.preview_bars(session, user, game, metric)
        cards = [
            DifficultyCard(
                difficulty=c["difficulty"],
                bar=c["bar"],
                clear_rate=c["clear_rate"],
                est_multiplier_bps=money_math.pool_multiplier_estimate_bps(
                    c["clear_rate"]
                ),
            )
            for c in preview["cards"]
        ]
        metrics.append(
            PoolMetric(
                metric=metric,
                label=metric_label(metric),
                provisional=preview["provisional"],
                cards=cards,
            )
        )
    return PoolMarketsResponse(
        game=game,
        linked=linked is not None,
        entry_presets_cents=list(ENTRY_PRESETS_CENTS),
        metrics=metrics,
    )


@router.post("/queue", response_model=PoolStatusResponse)
async def enter_pool(
    body: PoolEnterRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> PoolStatusResponse:
    result = await pool_engine.enqueue(
        session,
        user,
        game=body.game,
        metric=body.metric,
        difficulty=body.difficulty,
        entry_cents=body.entry_preset_cents,
    )
    return await _status_view(session, result, user)


@router.get("/queue/status", response_model=PoolStatusResponse)
async def queue_status(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> PoolStatusResponse:
    result = await pool_engine.poll_status(session, user)
    return await _status_view(session, result, user)


@router.delete("/queue", response_model=PoolStatusResponse)
async def leave_queue(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> PoolStatusResponse:
    await pool_engine.cancel(session, user)
    return PoolStatusResponse(status="idle")


@router.get("", response_model=PoolsListResponse)
async def list_pools(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> PoolsListResponse:
    status = await _status_view(
        session, await pool_engine.poll_status(session, user), user
    )
    rooms = list(
        await session.scalars(
            select(SoloPool)
            .join(SoloEntry, SoloEntry.pool_id == SoloPool.id)
            .where(SoloEntry.user_id == user.id)
            .order_by(SoloPool.created_at.desc())
            .limit(20)
        )
    )
    return PoolsListResponse(
        status=status,
        rooms=[await _pool_view(session, p, user) for p in rooms],
    )


@router.get("/{pool_id}", response_model=PoolView)
async def get_pool(
    pool_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> PoolView:
    pool = await session.get(SoloPool, pool_id)
    if pool is None:
        raise APIError("pool_not_found", "No such pool.", status_code=404)
    entry = await session.scalar(
        select(SoloEntry).where(
            SoloEntry.pool_id == pool_id, SoloEntry.user_id == user.id
        )
    )
    if entry is None:
        raise APIError("not_a_member", "You are not in this pool.", status_code=403)
    return await _pool_view(session, pool, user)
