"""Bucketing background jobs — the wiring that runs the tested engine on a clock.

`run_bucketing_cycle` is called from the worker loop. It is gated on the
`bucketing_enabled` flag **and** respects `settlement_paused`, so it moves no
money until the feature is turned on and it halts with the rest of the system on
a pause (fail closed).

Four jobs per cycle, each in its own short transaction (mirrors the settlement
worker's per-item pattern):

1. `ingest_active_accounts` — poll each ready-game linked account for new matches
   and fold them into the index/bucket via `state.record_and_update`. This is the
   only step that calls a game host; it is batched to bound host calls.
2. `form_pending_rooms` — form rooms from the bucket queues.
3. `settle_due_rooms` — attach each matched member's qualifying match (read from
   `match_stats` — no host call) and settle against the one bar; a member with no
   qualifying match by the deadline is refunded (fail closed, never guessed).
4. `expire_unfilled` — refund queue entries that never matched.

None of the money logic lives here — it all calls the Phase-1..7 services that are
already unit-tested. This module is the schedule and the plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .. import clock
from ..adapters import registry
from ..adapters.base import GameFilters
from ..constants import (
    FLAG_BUCKETING_ENABLED,
    FLAG_SETTLEMENT_PAUSED,
    GRADE_MATCH_SKEW_MS,
    rated_only_game,
)
from ..db.session import get_sessionmaker
from ..models.bucket_contest import BucketContest, BucketRoom
from ..models.bucketing import MatchStat
from ..models.linked_account import LinkedAccount
from ..services.bucketing import config as cfg
from ..services.bucketing import contest as contest_svc
from ..services.bucketing import ingestion
from ..services.bucketing import markets as mk
from ..services.bucketing import state as state_svc
from ..services.feature_flags import get_boolean_flags

# How many linked accounts to poll for new matches per cycle. Bounds host calls
# (PUBG's ~10 req/min budget); the settlement worker uses the same one-batch idea.
_INGEST_BATCH_PER_CYCLE = 5


@dataclass
class BucketingCycleReport:
    ran: bool = False
    paused: bool = False
    accounts_ingested: int = 0
    matches_ingested: int = 0
    rooms_formed: int = 0
    rooms_settled: int = 0
    entries_expired: int = 0
    markets_touched: list[str] = field(default_factory=list)


def _ready_games() -> list[str]:
    """Games whose mode discriminator is implemented (chess, PUBG today)."""
    return [g for g, ok in ingestion.MODE_GATE_READY.items() if ok]


# --------------------------------------------------------------------------- #
# 1. Ingest
# --------------------------------------------------------------------------- #


async def _ingest_since_ms(session: AsyncSession, player_id, game: str) -> int:
    """Poll cursor: newest match already recorded for this account (minus a small
    overlap so a match landing between polls is never skipped — `record_match` is
    idempotent, so re-seeing one is a harmless no-op)."""
    newest = await session.scalar(
        select(MatchStat.created_at_ms)
        .where(MatchStat.player_id == player_id, MatchStat.game == game)
        .order_by(MatchStat.created_at_ms.desc())
        .limit(1)
    )
    if not newest:
        return 0
    return max(0, int(newest) - GRADE_MATCH_SKEW_MS)


async def ingest_account(
    session: AsyncSession, link: LinkedAccount
) -> int:
    """Poll one linked account for new matches and fold them into the index.
    Returns how many *new* matches were recorded."""
    adapter = registry.get(link.game)
    if adapter is None:
        return 0
    since = await _ingest_since_ms(session, link.user_id, link.game)
    filters = GameFilters(rated_only=rated_only_game(link.game))
    try:
        games = await adapter.poll_eligible_games(link.host_account_id, since, filters)
    except Exception:
        # A host outage must not crash the cycle — skip this account this pass.
        return 0
    recorded = 0
    for norm in games:
        if await state_svc.record_and_update(session, link.user_id, link.game, norm):
            recorded += 1
    return recorded


async def ingest_active_accounts(
    sm: async_sessionmaker[AsyncSession],
    report: BucketingCycleReport,
    *,
    limit: int = _INGEST_BATCH_PER_CYCLE,
) -> None:
    ready = _ready_games()
    if not ready:
        return
    async with sm() as session:
        links = list(
            await session.scalars(
                select(LinkedAccount)
                .where(
                    LinkedAccount.status == "active",
                    LinkedAccount.game.in_(ready),
                )
                .order_by(LinkedAccount.created_at)
                .limit(limit)
            )
        )
    for link in links:
        async with sm() as session:
            fresh = await session.get(LinkedAccount, link.id)
            if fresh is None or fresh.status != "active":
                continue
            n = await ingest_account(session, fresh)
            await session.commit()
            report.accounts_ingested += 1
            report.matches_ingested += n


# --------------------------------------------------------------------------- #
# 2. Form rooms
# --------------------------------------------------------------------------- #


async def form_pending_rooms(
    sm: async_sessionmaker[AsyncSession],
    now: datetime,
    report: BucketingCycleReport,
) -> None:
    async with sm() as session:
        buckets = list(
            await session.execute(
                select(
                    BucketContest.game,
                    BucketContest.mode,
                    BucketContest.metric,
                    BucketContest.bucket,
                )
                .where(
                    BucketContest.status == cfg.STATUS_QUEUED,
                    BucketContest.room_id.is_(None),
                )
                .distinct()
            )
        )
    for game, mode, metric, bucket in buckets:
        async with sm() as session:
            # Is the oldest waiting entry past the fill window? Then allow a short
            # room; otherwise hold out for a full one.
            oldest = await session.scalar(
                select(BucketContest.created_at)
                .where(
                    BucketContest.game == game,
                    BucketContest.mode == mode,
                    BucketContest.metric == metric,
                    BucketContest.bucket == bucket,
                    BucketContest.status == cfg.STATUS_QUEUED,
                    BucketContest.room_id.is_(None),
                )
                .order_by(BucketContest.created_at)
                .limit(1)
            )
            allow_short = bool(
                oldest
                and (now - oldest).total_seconds() >= cfg.BUCKET_FILL_WINDOW_SECONDS
            )
            formed_any = False
            # Greedily form as many rooms as the queue supports this pass.
            while True:
                room = await contest_svc.form_room(
                    session, game, mode, metric, bucket, allow_short=allow_short
                )
                if room is None:
                    break
                report.rooms_formed += 1
                formed_any = True
            if formed_any:
                await session.commit()
                report.markets_touched.append(f"{game}:{mode}:{metric}")
            else:
                await session.rollback()


# --------------------------------------------------------------------------- #
# 3. Settle due rooms
# --------------------------------------------------------------------------- #


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


async def _attach_results(
    session: AsyncSession, room: BucketRoom, now: datetime
) -> None:
    """For each member with no result yet, find its first qualifying match in the
    log after `matched_at` and attach it."""
    members = await contest_svc._room_members(session, room.id)
    for m in members:
        if m.result_value is not None or m.qualifying_match_id is not None:
            continue
        if m.matched_at is None:
            continue
        cutoff = _to_ms(m.matched_at) - GRADE_MATCH_SKEW_MS
        match = await session.scalar(
            select(MatchStat)
            .where(
                MatchStat.player_id == m.player_id,
                MatchStat.game == m.game,
                MatchStat.mode == m.mode,
                MatchStat.created_at_ms >= cutoff,
            )
            .order_by(MatchStat.created_at_ms)
            .limit(1)
        )
        if match is None:
            continue
        value = (match.metrics or {}).get(m.metric)
        if value is None:
            continue
        await contest_svc.record_result(session, m, match.host_match_id, float(value))


async def settle_due_rooms(
    sm: async_sessionmaker[AsyncSession],
    now: datetime,
    report: BucketingCycleReport,
) -> None:
    async with sm() as session:
        room_ids = list(
            await session.scalars(
                select(BucketRoom.id).where(
                    BucketRoom.status == cfg.ROOM_AWAITING_RESULT
                )
            )
        )
    for room_id in room_ids:
        async with sm() as session:
            room = await session.scalar(
                select(BucketRoom)
                .where(
                    BucketRoom.id == room_id,
                    BucketRoom.status == cfg.ROOM_AWAITING_RESULT,
                )
                .with_for_update(skip_locked=True)
            )
            if room is None:
                continue
            await _attach_results(session, room, now)

            members = await contest_svc._room_members(session, room.id)
            all_in = all(m.status == cfg.STATUS_AWAITING_RESULT for m in members)
            # Deadline = the latest member's matched_at + the settle window.
            matched_ats = [m.matched_at for m in members if m.matched_at]
            deadline_passed = bool(matched_ats) and now >= (
                max(matched_ats) + timedelta(seconds=cfg.BUCKET_SETTLE_WINDOW_SECONDS)
            )
            if not all_in and not deadline_passed:
                await session.rollback()
                continue
            try:
                await contest_svc.settle_room(
                    session, room, force_deadline=deadline_passed
                )
                await session.commit()
                report.rooms_settled += 1
            except Exception:
                # Fail closed: never commit a half-applied settlement.
                await session.rollback()


# --------------------------------------------------------------------------- #
# 4. Expire unfilled
# --------------------------------------------------------------------------- #


async def expire_unfilled(
    sm: async_sessionmaker[AsyncSession],
    now: datetime,
    report: BucketingCycleReport,
) -> None:
    async with sm() as session:
        n = await contest_svc.expire_unfilled(session, now=now)
        if n:
            await session.commit()
            report.entries_expired += n
        else:
            await session.rollback()


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


async def run_bucketing_cycle(
    sm: async_sessionmaker[AsyncSession] | None = None,
    *,
    now: datetime | None = None,
) -> BucketingCycleReport:
    """One bucketing pass. No-op unless `bucketing_enabled` is on; halts if
    `settlement_paused` is on (fail closed)."""
    sm = sm or get_sessionmaker()
    now = now or clock.now()
    report = BucketingCycleReport()

    async with sm() as session:
        flags = await get_boolean_flags(session)
    if not flags.get(FLAG_BUCKETING_ENABLED, False):
        return report
    if flags.get(FLAG_SETTLEMENT_PAUSED, False):
        report.paused = True
        return report

    report.ran = True
    await ingest_active_accounts(sm, report)
    await form_pending_rooms(sm, now, report)
    await settle_due_rooms(sm, now, report)
    await expire_unfilled(sm, now, report)
    return report


# The set of markets, exposed for the nightly reference/promotion job wiring.
def all_markets() -> tuple[mk.BucketMarket, ...]:
    return mk.all_markets()
