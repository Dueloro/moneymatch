"""The settlement worker — a separate process, same codebase."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .. import clock
from ..constants import (
    FLAG_NIGHTLY_LAST_RUN,
    FLAG_QUEUE_PAUSED,
    FLAG_SETTLEMENT_PAUSED,
    FLAG_WORKER_HEARTBEAT,
    GRADING_ENGINE_VERSION,
    LIVE_SNAPSHOT_REFRESH_SECONDS,
    MATCH_MAX_LIFETIME_SECONDS,
    NIGHTLY_INTERVAL_SECONDS,
    TOURNAMENT_STANDINGS_REFRESH_SECONDS,
    WORKER_POLL_INTERVAL_SECONDS,
)
from ..db.session import get_sessionmaker
from ..models.feature_flag import FeatureFlag
from ..models.live import LiveSnapshot
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from ..services import (
    challenge_service,
    grading,
    live_activity_service,
    match_lifecycle,
    matchmaking,
    metric_models_service,
    pool_engine,
    raw_payload_service,
    telemetry_fetch,
    tournament_engine,
)
from ..services.feature_flags import get_boolean_flags
from ..services.match_lifecycle import (
    CANCEL,
    PUSH,
    WIN,
    ReconciliationError,
    SettlementResult,
)
from ..services.match_states import ACTIVE, AWAITING_RESULT, PENDING

log = structlog.get_logger(__name__)


class SettlementHalted(Exception):
    """Raised to stop the loop after a fail-closed reconciliation breach."""


@dataclass
class CycleReport:
    settled: int = 0
    pushed: int = 0
    canceled: int = 0
    pending: int = 0
    expired_pending: int = 0
    expired_tickets: int = 0
    drained_tickets: int = 0
    pools_settled: int = 0
    tournaments_settled: int = 0
    standings_refreshed: int = 0
    live_refreshed: int = 0
    expired_challenges: int = 0
    paused: bool = False


async def _flag(session: AsyncSession, key: str) -> bool:
    return (await get_boolean_flags(session)).get(key, False)


async def _set_flag(
    sm: async_sessionmaker[AsyncSession], key: str, value: bool
) -> None:
    async with sm() as session:
        await session.execute(
            update(FeatureFlag).where(FeatureFlag.key == key).values(enabled=value)
        )
        await session.commit()


async def _write_heartbeat(sm: async_sessionmaker[AsyncSession], now: datetime) -> None:
    from ..services import feature_flags

    async with sm() as session:
        await feature_flags.set_flag(
            session,
            FLAG_WORKER_HEARTBEAT,
            enabled=True,
            payload={"ts": now.isoformat()},
        )
        await session.commit()


async def resolve_match(session: AsyncSession, match: Match, now: datetime) -> str:
    """Public entry to the grade+settle path for one match."""
    return await _resolve_match(session, match, now)


async def _resolve_match(session: AsyncSession, match: Match, now: datetime) -> str:
    seats = await match_lifecycle.players(session, match.id)
    outcome = await grading.grade(match, seats, now)

    if outcome.status == grading.PENDING:
        # Hard ceiling from matched_at → CANCEL + refund (outage can't strand money).
        if match.matched_at is not None and now >= match.matched_at + timedelta(
            seconds=MATCH_MAX_LIFETIME_SECONDS
        ):
            await match_lifecycle.settle(
                session,
                match,
                SettlementResult(
                    kind=CANCEL,
                    outcome_detail={"reason": "hard_ceiling"},
                    engine_version=GRADING_ENGINE_VERSION,
                ),
            )
            return "canceled"
        if outcome.host_error:
            _extend_window(match, now)
        if match.state == ACTIVE:
            match.state = AWAITING_RESULT
        await session.flush()
        return "pending"

    payload = await raw_payload_service.persist(
        session,
        f"grade:{match.game}",
        {
            "match_id": str(match.id),
            "market": match.market,
            "status": outcome.status,
            "detail": outcome.detail,
            "stat_lines": {str(k): v for k, v in outcome.stat_lines.items()},
        },
        memo=f"settle {match.market}",
    )
    kind = {grading.WIN: WIN, grading.PUSH: PUSH, grading.CANCEL: CANCEL}[
        outcome.status
    ]
    await match_lifecycle.settle(
        session,
        match,
        SettlementResult(
            kind=kind,
            winner_user_id=outcome.winner_user_id,
            stat_lines=outcome.stat_lines,
            outcome_detail=outcome.detail,
            engine_version=GRADING_ENGINE_VERSION,
            raw_payload_id=payload.id,
        ),
    )
    return {"win": "settled", "push": "pushed", "cancel": "canceled"}[kind]


def _extend_window(match: Match, now: datetime) -> None:
    if match.matched_at is None or match.window_ends_at is None:
        return
    ceiling = match.matched_at + timedelta(seconds=MATCH_MAX_LIFETIME_SECONDS)
    extended = match.window_ends_at + timedelta(seconds=WORKER_POLL_INTERVAL_SECONDS)
    match.window_ends_at = min(extended, ceiling)


async def _process_due_matches(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        ids = list(
            await session.scalars(
                select(Match.id).where(Match.state.in_((ACTIVE, AWAITING_RESULT)))
            )
        )

    for match_id in ids:
        async with sm() as session:
            match = await _claim(session, match_id)
            if match is None:
                continue  # locked by another worker, or already terminal
            try:
                result = await _resolve_match(session, match, now)
                await session.commit()
            except ReconciliationError as exc:
                await session.rollback()
                log.error(
                    "settlement.reconciliation_breach",
                    match_id=str(match_id),
                    violations=exc.detail,
                )
                await _set_flag(sm, FLAG_SETTLEMENT_PAUSED, True)
                report.paused = True
                raise SettlementHalted from exc
            _tally(report, result)
            if result in ("settled", "pushed"):
                await _refresh_after_settle(sm, match_id)


async def _refresh_after_settle(
    sm: async_sessionmaker[AsyncSession], match_id: uuid.UUID
) -> None:
    try:
        async with sm() as session:
            match = await session.get(Match, match_id)
            if match is None:
                return
            seats = await match_lifecycle.players(session, match_id)
            for seat in seats:
                await metric_models_service.bootstrap(
                    session, seat.user_id, match.game, seat.host_account_id
                )
            await session.commit()
    except Exception:  # noqa: BLE001 — refresh is advisory; settlement already landed
        log.warning(
            "settlement.metric_refresh_failed", match_id=str(match_id), exc_info=True
        )


async def _claim(session: AsyncSession, match_id: uuid.UUID) -> Match | None:
    match = await session.scalar(
        select(Match)
        .where(Match.id == match_id, Match.state.in_((ACTIVE, AWAITING_RESULT)))
        .with_for_update(skip_locked=True)
    )
    return match


def _tally(report: CycleReport, result: str) -> None:
    if result == "settled":
        report.settled += 1
    elif result == "pushed":
        report.pushed += 1
    elif result == "canceled":
        report.canceled += 1
    elif result == "pending":
        report.pending += 1


async def _expire_pending_matches(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        ids = list(
            await session.scalars(
                select(Match.id).where(
                    Match.state == PENDING,
                    Match.window_ends_at.isnot(None),
                    Match.window_ends_at <= now,
                )
            )
        )
    for match_id in ids:
        async with sm() as session:
            match = await session.scalar(
                select(Match)
                .where(Match.id == match_id, Match.state == PENDING)
                .with_for_update(skip_locked=True)
            )
            if match is None:
                continue
            await match_lifecycle.cancel_pending(session, match, reason="expired")
            await session.commit()
            report.expired_pending += 1


async def _expire_tickets(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        report.expired_tickets += await matchmaking.expire_tickets(session, now=now)
        await session.commit()


async def _expire_challenges(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        report.expired_challenges += await challenge_service.expire_due(
            session, now=now
        )
        await session.commit()


async def _drain_queue_if_paused(
    sm: async_sessionmaker[AsyncSession], report: CycleReport
) -> None:
    async with sm() as session:
        if await _flag(session, FLAG_QUEUE_PAUSED):
            report.drained_tickets += await matchmaking.cancel_all_waiting(session)
            await session.commit()


async def _process_due_pools(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        ids = list(
            await session.scalars(
                select(SoloPool.id).where(
                    SoloPool.state == "LOCKED",
                    or_(
                        SoloPool.window_ends_at <= now,
                        SoloPool.outcome_detail["live_ready"].astext == "true",
                    ),
                )
            )
        )
    for pool_id in ids:
        async with sm() as session:
            pool = await session.scalar(
                select(SoloPool)
                .where(SoloPool.id == pool_id, SoloPool.state == "LOCKED")
                .with_for_update(skip_locked=True)
            )
            if pool is None:
                continue
            entries = list(
                await session.scalars(
                    select(SoloEntry).where(SoloEntry.pool_id == pool_id)
                )
            )
            grades = await telemetry_fetch.grade_pool(session, pool, entries)
            # If the live flag was optimistic (a grade still comes back unverifiable),
            # leave the pool for a later cycle / the window-end path, which refunds the
            # unverifiable entries correctly.
            window_over = pool.window_ends_at <= now
            all_verified = bool(grades) and all(
                g.cleared is not None for g in grades.values()
            )
            if not window_over and not all_verified:
                await session.rollback()
                continue
            try:
                await pool_engine.settle_pool(session, pool, grades)
                await session.commit()
            except ReconciliationError as exc:
                await session.rollback()
                await _halt_on_breach(sm, report, "solo_pool", pool_id, exc)
                raise SettlementHalted from exc
            report.pools_settled += 1


async def _process_due_tournaments(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        ids = list(
            await session.scalars(
                select(Tournament.id).where(
                    Tournament.state == "LOCKED", Tournament.window_ends_at <= now
                )
            )
        )
    for tid in ids:
        async with sm() as session:
            tournament = await session.scalar(
                select(Tournament)
                .where(Tournament.id == tid, Tournament.state == "LOCKED")
                .with_for_update(skip_locked=True)
            )
            if tournament is None:
                continue
            entries = list(
                await session.scalars(
                    select(TournamentEntry).where(TournamentEntry.tournament_id == tid)
                )
            )
            grades = await telemetry_fetch.grade_tournament(
                session, tournament, entries
            )
            try:
                await tournament_engine.settle_tournament(session, tournament, grades)
                await session.commit()
            except ReconciliationError as exc:
                await session.rollback()
                await _halt_on_breach(sm, report, "tournament", tid, exc)
                raise SettlementHalted from exc
            report.tournaments_settled += 1


async def _refresh_tournament_standings(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        ids = list(
            await session.scalars(
                select(Tournament.id).where(
                    Tournament.state == "LOCKED", Tournament.window_ends_at > now
                )
            )
        )
    for tid in ids:
        async with sm() as session:
            tournament = await session.get(Tournament, tid)
            if tournament is None or tournament.state != "LOCKED":
                continue
            fresh_enough = (
                tournament.standings_updated_at is not None
                and (now - tournament.standings_updated_at).total_seconds()
                < TOURNAMENT_STANDINGS_REFRESH_SECONDS
            )
            if fresh_enough:
                continue
            entries = list(
                await session.scalars(
                    select(TournamentEntry).where(TournamentEntry.tournament_id == tid)
                )
            )
            names = await _usernames(session, [e.user_id for e in entries])
            standings = await telemetry_fetch.live_standings(
                session, tournament, entries, names
            )
            tournament.standings_cache = {"rows": standings}
            tournament.standings_updated_at = now
            await session.commit()
            report.standings_refreshed += 1


async def _live_is_fresh(
    session: AsyncSession, ref_type: str, ref_id: uuid.UUID, now: datetime
) -> bool:
    row = await session.get(LiveSnapshot, (ref_type, ref_id))
    return (
        row is not None
        and (now - row.updated_at).total_seconds() < LIVE_SNAPSHOT_REFRESH_SECONDS
    )


async def _upsert_live(
    session: AsyncSession,
    ref_type: str,
    ref_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> None:
    row = await session.get(LiveSnapshot, (ref_type, ref_id))
    if row is None:
        session.add(
            LiveSnapshot(ref_type=ref_type, ref_id=ref_id, data=data, updated_at=now)
        )
    else:
        row.data = data
        row.updated_at = now


async def _refresh_live_snapshots(
    sm: async_sessionmaker[AsyncSession], now: datetime, report: CycleReport
) -> None:
    async with sm() as session:
        pool_ids = list(
            await session.scalars(
                select(SoloPool.id).where(
                    SoloPool.state == "LOCKED", SoloPool.window_ends_at > now
                )
            )
        )
    for pid in pool_ids:
        async with sm() as session:
            pool = await session.get(SoloPool, pid)
            if pool is None or pool.state != "LOCKED":
                continue
            if await _live_is_fresh(session, "pool", pid, now):
                continue
            entries = list(
                await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pid))
            )
            snapshot = await live_activity_service.build_pool_snapshot(
                session, pool, entries
            )
            await _upsert_live(session, "pool", pid, snapshot, now)
            if live_activity_service.pool_all_decided(snapshot):
                pool.outcome_detail = {
                    **(pool.outcome_detail or {}),
                    "live_ready": True,
                }
            await session.commit()
            report.live_refreshed += 1

    async with sm() as session:
        match_ids = list(
            await session.scalars(
                select(Match.id).where(
                    Match.state.in_(("ACTIVE", "AWAITING_RESULT")),
                    Match.matched_at.isnot(None),
                )
            )
        )
    for mid in match_ids:
        async with sm() as session:
            match = await session.get(Match, mid)
            if match is None or match.state not in ("ACTIVE", "AWAITING_RESULT"):
                continue
            if await _live_is_fresh(session, "match", mid, now):
                continue
            seats = list(
                await session.scalars(
                    select(MatchPlayer).where(MatchPlayer.match_id == mid)
                )
            )
            match_snapshot = await live_activity_service.build_match_snapshot(
                session, match, seats
            )
            if match_snapshot is None:
                continue
            await _upsert_live(session, "match", mid, match_snapshot, now)
            await session.commit()
            report.live_refreshed += 1


async def _usernames(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


async def _halt_on_breach(
    sm: async_sessionmaker[AsyncSession],
    report: CycleReport,
    ref_type: str,
    ref_id: uuid.UUID,
    exc: ReconciliationError,
) -> None:
    log.error(
        "settlement.reconciliation_breach",
        ref_type=ref_type,
        ref_id=str(ref_id),
        violations=exc.detail,
    )
    await _set_flag(sm, FLAG_SETTLEMENT_PAUSED, True)
    report.paused = True


async def run_cycle(
    sm: async_sessionmaker[AsyncSession] | None = None,
    *,
    now: datetime | None = None,
) -> CycleReport:
    """One full worker pass."""
    sm = sm or get_sessionmaker()
    now = now or clock.now()
    report = CycleReport()

    await _write_heartbeat(sm, now)

    async with sm() as session:
        if await _flag(session, FLAG_SETTLEMENT_PAUSED):
            report.paused = True
            return report

    try:
        await _process_due_matches(sm, now, report)
        await _process_due_pools(sm, now, report)
        await _process_due_tournaments(sm, now, report)
    except SettlementHalted:
        return report
    await _refresh_tournament_standings(sm, now, report)
    await _refresh_live_snapshots(sm, now, report)
    await _expire_pending_matches(sm, now, report)
    await _expire_tickets(sm, now, report)
    await _expire_challenges(sm, now, report)
    await _drain_queue_if_paused(sm, report)
    return report


async def _nightly_due(sm: async_sessionmaker[AsyncSession], now: datetime) -> bool:
    async with sm() as session:
        flag = await session.scalar(
            select(FeatureFlag).where(FeatureFlag.key == FLAG_NIGHTLY_LAST_RUN)
        )
    if flag is None or not flag.payload or "ts" not in flag.payload:
        return True
    last = datetime.fromisoformat(flag.payload["ts"])
    return (now - last).total_seconds() >= NIGHTLY_INTERVAL_SECONDS


async def _mark_nightly_ran(
    sm: async_sessionmaker[AsyncSession], now: datetime
) -> None:
    from ..services import feature_flags

    async with sm() as session:
        await feature_flags.set_flag(
            session,
            FLAG_NIGHTLY_LAST_RUN,
            enabled=True,
            payload={"ts": now.isoformat()},
        )
        await session.commit()


async def maybe_run_nightly(
    sm: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> bool:
    """Run the nightly pass if due, then stamp the last-run flag."""
    now = now or clock.now()
    if not await _nightly_due(sm, now):
        return False
    from .nightly import run_nightly

    await run_nightly(sm, now=now)
    await _mark_nightly_ran(sm, now)
    return True


async def run_forever(interval: int = WORKER_POLL_INTERVAL_SECONDS) -> None:
    sm = get_sessionmaker()
    log.info("settlement_worker.start", interval=interval)
    while True:
        try:
            report = await run_cycle(sm)
            if report.settled or report.pushed or report.canceled or report.paused:
                log.info("settlement_worker.cycle", **report.__dict__)
            await maybe_run_nightly(sm)
        except Exception:  # noqa: BLE001 — never let the loop die on one bad cycle
            log.exception("settlement_worker.cycle_failed")
        await asyncio.sleep(interval)


def main() -> None:
    from ..config import get_settings
    from ..logging import configure_logging
    from ..observability import init_sentry

    settings = get_settings()
    configure_logging(settings)
    init_sentry(settings)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
