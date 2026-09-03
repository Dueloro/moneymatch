"""`/bucketing` — the API surface for the one-bar-per-bucket system.

Thin endpoints: each validates, calls an already-tested bucketing service, and
returns state. No rating/settlement maths lives here. Every route is a no-op or a
404 unless the `bucketing_enabled` flag is on (the whole feature ships dark).

Money still moves only inside the services (through `wallet_service`), inside the
request transaction that `get_session` commits.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import FLAG_BUCKETING_ENABLED, metric_label
from ..db.session import get_session
from ..dependencies import CurrentUser, require_admin
from ..errors import APIError
from ..models.bucket_contest import BucketContest
from ..models.user import User
from ..schemas.bucketing import (
    ContestStatus,
    DisputeRequest,
    DisputeResponse,
    MarketCard,
    MarketsResponse,
    ResolveRequest,
    WagerRequest,
)
from ..services.bucketing import contest as contest_svc
from ..services.bucketing import disputes as dispute_svc
from ..services.bucketing import markets as mk
from ..services.bucketing import placement as pl
from ..services.bucketing import state as state_svc
from ..services.feature_flags import get_boolean_flags

router = APIRouter(prefix="/bucketing", tags=["bucketing"])


async def _enabled(session: AsyncSession) -> bool:
    flags = await get_boolean_flags(session)
    return bool(flags.get(FLAG_BUCKETING_ENABLED, False))


async def _require_enabled(session: AsyncSession) -> None:
    if not await _enabled(session):
        raise APIError(
            "bucketing_not_enabled",
            "Bucketed markets aren't available yet.",
            status_code=404,
        )


def _status_view(c: BucketContest) -> ContestStatus:
    return ContestStatus(
        contest_id=c.id,
        game=c.game,
        mode=c.mode,
        metric=c.metric,
        bucket=c.bucket,
        status=c.status,
        stake_cents=c.stake_cents,
        bar=c.bar,
        result_value=c.result_value,
        cleared=c.cleared,
        payout_cents=c.payout_cents,
        room_id=c.room_id,
    )


@router.get("/markets", response_model=MarketsResponse)
async def get_markets(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> MarketsResponse:
    """Every bucketed market, with the caller's placement + stake cap for each.

    When the feature is off this returns `enabled: false` and an empty list rather
    than a 404, so the app can hide the section gracefully.
    """
    if not await _enabled(session):
        return MarketsResponse(enabled=False, markets=[])

    cards: list[MarketCard] = []
    for market in mk.all_markets():
        ms = await state_svc.get_market_state(
            session, user.id, market.game, market.mode, market.metric
        )
        placed = ms is not None and ms.bucket is not None
        bar = None
        cap = pl.LADDER_CAPS_CENTS[0]  # default floor cap when unplaced
        provisional = True
        bucket = None
        if placed:
            bucket = ms.bucket
            provisional = ms.provisional
            cap = pl.stake_cap_cents(ms.index_confidence, provisional=ms.provisional)
            ref = await state_svc.get_active_reference(
                session, market.game, market.mode, market.metric
            )
            if ref is not None and ms.bucket < len(ref.bars):
                bar = ref.bars[ms.bucket]
        cards.append(
            MarketCard(
                game=market.game,
                mode=market.mode,
                metric=market.metric,
                label=metric_label(market.metric),
                placed=placed,
                bucket=bucket,
                bar=bar,
                stake_cap_cents=cap,
                provisional=provisional,
                multiplier_bps=contest_svc.multiplier_bps(),
            )
        )
    return MarketsResponse(enabled=True, markets=cards)


@router.post("/wagers", response_model=ContestStatus)
async def place_wager(
    body: WagerRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ContestStatus:
    await _require_enabled(session)
    market = mk.get(body.game, body.mode, body.metric)
    if market is None:
        raise APIError("unknown_market", "No such market.", status_code=404)
    contest = await contest_svc.enter_wager(session, user.id, market, body.stake_cents)
    return _status_view(contest)


async def _load_contest(
    session: AsyncSession, contest_id: UUID, user: User, *, allow_admin: bool = False
) -> BucketContest:
    c = await session.get(BucketContest, contest_id)
    if c is None:
        raise APIError("contest_not_found", "No such contest.", status_code=404)
    if c.player_id != user.id and not (allow_admin and user.role == "admin"):
        raise APIError("not_your_contest", "Not your contest.", status_code=403)
    return c


@router.get("/contests/{contest_id}", response_model=ContestStatus)
async def contest_status(
    contest_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ContestStatus:
    await _require_enabled(session)
    c = await _load_contest(session, contest_id, user)
    return _status_view(c)


@router.get("/contests/{contest_id}/explain")
async def explain_contest(
    contest_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _require_enabled(session)
    await _load_contest(session, contest_id, user, allow_admin=True)
    return await dispute_svc.explain_contest(session, contest_id)


@router.post("/disputes", response_model=DisputeResponse)
async def open_dispute(
    body: DisputeRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> DisputeResponse:
    await _require_enabled(session)
    dispute = await dispute_svc.open_dispute(
        session, body.contest_id, user.id, body.reason
    )
    return DisputeResponse(
        dispute_id=dispute.id, status=dispute.status, hold=dispute.hold
    )


@router.post("/admin/disputes/{dispute_id}/resolve", response_model=DisputeResponse)
async def resolve_dispute(
    dispute_id: UUID,
    body: ResolveRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DisputeResponse:
    await _require_enabled(session)
    actor = admin.username or str(admin.id)
    if body.resolution == "clawback":
        if not body.fault_player_ids:
            raise APIError(
                "fault_required",
                "A clawback needs at least one fault player.",
                status_code=422,
            )
        dispute = await dispute_svc.resolve_with_clawback(
            session, dispute_id, body.fault_player_ids, admin=actor, note=body.note
        )
    else:
        mapped = {
            "no_change": "resolved_no_change",
            "refund": "resolved_refund",
            "adjust": "resolved_adjust",
        }.get(body.resolution, body.resolution)
        dispute = await dispute_svc.resolve_dispute(
            session, dispute_id, mapped, admin=actor, note=body.note
        )
    return DisputeResponse(
        dispute_id=dispute.id, status=dispute.status, hold=dispute.hold
    )
