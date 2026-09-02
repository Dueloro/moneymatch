"""Phase 5 — the wager path, room formation & settlement (DB + wallet).

Ties the proven `settlement.settle_room` money maths to the wallet and the
`bucket_contest` / `bucket_room` tables. The flow, from
`BUCKETING_TECHNICAL_WALKTHROUGH.md` §7–§8:

    enter_wager   → validate placement + cap, hold the stake, queue the entry
    form_room     → gather same-bucket queued entries into a room, snapshot the
                    active reference's bar (so a later re-cut can't change how the
                    room grades)
    record_result → attach a player's qualifying metric value to their entry
    settle_room   → grade every member vs the one bar, move money, write the
                    settlement + audit rows. Fail-closed: unverifiable data or a
                    no-clear room refunds; the money invariant is asserted before
                    anything commits.

Every function flushes but never commits — the caller (worker/request) owns the
transaction boundary, exactly like `wallet_service`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...errors import APIError
from ...models.bucket_contest import BucketContest, BucketRoom
from ...models.bucketing import AuditEvent, Settlement
from ...services import money_math, wallet_service
from . import config as cfg
from . import markets as mk
from . import placement as pl
from . import settlement as st
from . import state as stmod


class BucketWagerError(APIError):
    """A wager was rejected before any money moved (RFC-7807 envelope)."""


def _now() -> datetime:
    return datetime.now(UTC)


async def _audit(
    session: AsyncSession,
    *,
    event_type: str,
    player_id: uuid.UUID | None = None,
    market: str | None = None,
    contest_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    actor: str = "system",
    reason: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            player_id=player_id,
            event_type=event_type,
            market=market,
            contest_id=contest_id,
            before=before,
            after=after,
            actor=actor,
            reason=reason,
        )
    )


# --------------------------------------------------------------------------- #
# 1. Enter a wager
# --------------------------------------------------------------------------- #


async def enter_wager(
    session: AsyncSession,
    player_id: uuid.UUID,
    market: mk.BucketMarket,
    stake_cents: int,
) -> BucketContest:
    """Validate placement + the confidence-gated stake cap, hold the stake, and
    queue the entry. Raises `BucketWagerError` (no money moved) on any rejection.
    """
    if stake_cents <= 0:
        raise BucketWagerError(
            "invalid_stake", "Stake must be positive.", status_code=422
        )

    ms = await stmod.get_market_state(
        session, player_id, market.game, market.mode, market.metric
    )
    if ms is None or ms.bucket is None:
        raise BucketWagerError(
            "not_placed",
            "You aren't placed in this market yet — play a qualifying match first.",
            status_code=409,
        )

    cap = pl.stake_cap_cents(ms.index_confidence, provisional=ms.provisional)
    if not pl.within_cap(stake_cents, cap):
        raise BucketWagerError(
            "stake_over_cap",
            "Stake exceeds your current cap for this market.",
            status_code=422,
            detail={"cap_cents": cap, "stake_cents": stake_cents},
        )

    # Pre-check the one-open-wager-per-market rule and fail cleanly. The partial
    # unique index (migration 0029) is the race-safe backstop; catching it here
    # keeps the caller's transaction from being poisoned by a DB violation on the
    # common, non-racing case.
    existing = await session.scalar(
        select(BucketContest.id).where(
            BucketContest.player_id == player_id,
            BucketContest.game == market.game,
            BucketContest.mode == market.mode,
            BucketContest.metric == market.metric,
            BucketContest.status.in_(
                (cfg.STATUS_QUEUED, cfg.STATUS_MATCHED, cfg.STATUS_AWAITING_RESULT)
            ),
        )
    )
    if existing is not None:
        raise BucketWagerError(
            "already_wagering",
            "You already have an open wager in this market.",
            status_code=409,
        )

    contest = BucketContest(
        player_id=player_id,
        game=market.game,
        mode=market.mode,
        metric=market.metric,
        bucket=ms.bucket,
        stake_cents=stake_cents,
        status=cfg.STATUS_QUEUED,
    )
    session.add(contest)
    await session.flush()

    # Hold the stake (available → escrow) in the same transaction.
    await wallet_service.escrow_hold(
        session,
        player_id,
        stake_cents,
        ref_type="bucket_contest",
        ref_id=contest.id,
        memo=f"bucket wager {market.key_str}",
    )
    await _audit(
        session,
        event_type="wager_entered",
        player_id=player_id,
        market=market.key_str,
        contest_id=str(contest.id),
        after={"stake_cents": stake_cents, "bucket": ms.bucket},
    )
    return contest


# --------------------------------------------------------------------------- #
# 2. Form a room (the matchmaker)
# --------------------------------------------------------------------------- #


async def form_room(
    session: AsyncSession,
    game: str,
    mode: str,
    metric: str,
    bucket: int,
    *,
    allow_short: bool = False,
) -> BucketRoom | None:
    """Form one room from the head of a bucket's queue.

    Returns the room, or None if there aren't enough waiting entries. `allow_short`
    lets the fill-window expiry form a room down to `BUCKET_MIN_ROOM`; otherwise a
    full `BUCKET_ROOM_SIZE` is required. All members settle against the one bar
    read from the market's **active** reference at formation time.
    """
    min_needed = cfg.BUCKET_MIN_ROOM if allow_short else cfg.BUCKET_ROOM_SIZE

    # Lock the head of the queue so two matchmaker passes can't grab the same
    # entries (skip rows another pass already locked).
    rows = (
        await session.execute(
            select(BucketContest)
            .where(
                BucketContest.game == game,
                BucketContest.mode == mode,
                BucketContest.metric == metric,
                BucketContest.bucket == bucket,
                BucketContest.status == cfg.STATUS_QUEUED,
                BucketContest.room_id.is_(None),
            )
            .order_by(BucketContest.created_at)
            .limit(cfg.BUCKET_ROOM_SIZE)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()

    if len(rows) < min_needed:
        return None

    ref = await stmod.get_active_reference(session, game, mode, metric)
    if ref is None or bucket >= len(ref.bars):
        # No active reference / bar for this bucket yet — cannot grade a room, so
        # don't form one (the entries stay queued).
        return None

    room = BucketRoom(
        game=game,
        mode=mode,
        metric=metric,
        bucket=bucket,
        reference_season=ref.season,
        reference_version=ref.version,
        bar=ref.bars[bucket],
        lower_is_better=ref.lower_is_better,
        status=cfg.ROOM_OPEN,
        pot_cents=sum(r.stake_cents for r in rows),
    )
    session.add(room)
    await session.flush()

    now = _now()
    for r in rows:
        r.room_id = room.id
        r.status = cfg.STATUS_MATCHED
        r.matched_at = now
        r.reference_season = ref.season
        r.reference_version = ref.version
        r.bar = ref.bars[bucket]
    room.status = cfg.ROOM_AWAITING_RESULT
    await session.flush()
    await _audit(
        session,
        event_type="room_formed",
        market=f"{game}:{mode}:{metric}",
        after={"room_id": str(room.id), "bucket": bucket, "members": len(rows)},
    )
    return room


# --------------------------------------------------------------------------- #
# 3. Attach a qualifying result
# --------------------------------------------------------------------------- #


async def record_result(
    session: AsyncSession,
    contest: BucketContest,
    match_id: str,
    value: float | None,
) -> None:
    """Attach a player's qualifying match result to their (matched) entry.

    `value=None` marks the result unverifiable — settlement will void/refund the
    whole room rather than grade a guess.
    """
    contest.qualifying_match_id = match_id
    contest.result_value = value
    contest.status = cfg.STATUS_AWAITING_RESULT
    await session.flush()


# --------------------------------------------------------------------------- #
# 4. Settle a room
# --------------------------------------------------------------------------- #


async def _room_members(
    session: AsyncSession, room_id: uuid.UUID
) -> list[BucketContest]:
    return list(
        (
            await session.execute(
                select(BucketContest).where(BucketContest.room_id == room_id)
            )
        )
        .scalars()
        .all()
    )


def _all_results_in(members: list[BucketContest]) -> bool:
    return all(m.status == cfg.STATUS_AWAITING_RESULT for m in members)


async def settle_room(
    session: AsyncSession,
    room: BucketRoom,
    *,
    force_deadline: bool = False,
) -> BucketRoom:
    """Grade every member against the room's one bar and move the money.

    Only settles once every member has a result, unless `force_deadline` (the
    settle-window expiry) forces it — a member with no result then counts as
    unverifiable, which refunds the whole room (fail closed). Idempotent: a room
    not in `awaiting_result` is returned untouched.
    """
    if room.status != cfg.ROOM_AWAITING_RESULT:
        return room

    members = await _room_members(session, room.id)
    if not force_deadline and not _all_results_in(members):
        return room  # still waiting on someone

    mrs = [
        st.MemberResult(
            player_id=str(m.player_id),
            stake_cents=m.stake_cents,
            # A member with no result at the deadline is unverifiable → refund.
            result_value=(
                m.result_value
                if m.status == cfg.STATUS_AWAITING_RESULT
                else None
            ),
        )
        for m in members
    ]

    outcome = st.settle_room(mrs, room.bar, lower_is_better=room.lower_is_better)

    # Move the money. money_math already guarantees reconciliation; the wallet
    # legs mirror the outcome exactly.
    if outcome.refunded:
        for m in members:
            await wallet_service.refund(
                session,
                m.player_id,
                m.stake_cents,
                ref_type="bucket_contest",
                ref_id=m.id,
                memo="bucket refund",
            )
            m.status = cfg.STATUS_REFUNDED
            m.payout_cents = m.stake_cents
            m.settled_at = _now()
        room.status = cfg.ROOM_REFUNDED
        room.rake_cents = 0
    else:
        for m in members:
            # Consume the staked escrow (funds the pot).
            await wallet_service.escrow_release(
                session,
                m.player_id,
                m.stake_cents,
                ref_type="bucket_contest",
                ref_id=m.id,
                memo="bucket stake consumed",
            )
            pay = outcome.payouts.get(str(m.player_id), 0)
            m.cleared = pay > 0
            m.payout_cents = pay
            if pay > 0:
                await wallet_service.payout(
                    session,
                    m.player_id,
                    pay,
                    ref_type="bucket_contest",
                    ref_id=m.id,
                    memo="bucket winnings",
                )
            m.status = cfg.STATUS_SETTLED
            m.settled_at = _now()
        await wallet_service.rake(
            session,
            outcome.rake_cents,
            ref_type="bucket_room",
            ref_id=room.id,
            memo="bucket rake",
        )
        room.status = cfg.ROOM_SETTLED
        room.rake_cents = outcome.rake_cents

    room.settled_at = _now()

    # Write the append-only settlement audit row per member + an audit_event.
    winners = sum(1 for m in members if (m.cleared or False))
    for m in members:
        session.add(
            Settlement(
                contest_id=str(m.id),
                player_id=m.player_id,
                game=room.game,
                mode=room.mode,
                metric=room.metric,
                bucket=room.bucket,
                bar=room.bar,
                reference_season=room.reference_season,
                reference_version=room.reference_version,
                result_value=m.result_value,
                cleared=bool(m.cleared) if m.cleared is not None else False,
                stake_cents=m.stake_cents,
                payout_cents=m.payout_cents,
                rake_cents=(room.rake_cents if m is members[0] else 0),
                refunded=outcome.refunded,
            )
        )
    await _audit(
        session,
        event_type="room_settled" if not outcome.refunded else "room_refunded",
        market=f"{room.game}:{room.mode}:{room.metric}",
        after={
            "room_id": str(room.id),
            "pot_cents": outcome.pot_cents,
            "rake_cents": outcome.rake_cents,
            "winners": winners,
            "reason": outcome.reason,
        },
    )
    await session.flush()
    return room


# --------------------------------------------------------------------------- #
# 5. Expiry — unfilled queue entries refund and cancel
# --------------------------------------------------------------------------- #


async def expire_unfilled(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Refund + cancel queued entries older than the fill window that never made a
    room. Returns how many were expired. (The matchmaker should first try a short
    room; anything still unmatched past the window is refunded, never mismatched.)
    """
    now = now or _now()
    cutoff = now - timedelta(seconds=cfg.BUCKET_FILL_WINDOW_SECONDS)
    stale = (
        (
            await session.execute(
                select(BucketContest)
                .where(
                    BucketContest.status == cfg.STATUS_QUEUED,
                    BucketContest.room_id.is_(None),
                    BucketContest.created_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for c in stale:
        await wallet_service.refund(
            session,
            c.player_id,
            c.stake_cents,
            ref_type="bucket_contest",
            ref_id=c.id,
            memo="bucket queue expired",
        )
        c.status = cfg.STATUS_CANCELED
        c.settled_at = now
        await _audit(
            session,
            event_type="wager_canceled",
            player_id=c.player_id,
            market=f"{c.game}:{c.mode}:{c.metric}",
            contest_id=str(c.id),
            reason="fill window expired",
        )
    await session.flush()
    return len(stale)


def multiplier_bps(rake_bps: int = money_math.DEFAULT_RAKE_BPS) -> int:
    """Display multiplier for a bucket wager — derived pot math, never a line."""
    return money_math.h2h_multiplier_bps(rake_bps)
