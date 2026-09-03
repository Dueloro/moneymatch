"""The bucketing nightly pass — references, promotion advice, anomaly sweep.

Called from `run_nightly` (behind `bucketing_enabled`). Three bounded sweeps:

1. **Ensure a reference exists.** A market can't form rooms without an active
   `market_reference`. At launch this is seeded from public data; failing that,
   once a market has enough of its own players this bootstraps version 1 from the
   live population. It only ever *creates the first* reference automatically —
   re-cutting an existing market is the controlled promote/demote path
   (`promotion.apply_recut`), never a silent nightly change.
2. **Promotion advice.** Run the three gates and record the recommended K + the
   binding gate as an `audit_events` row. Advisory only: applying a re-cut is a
   deliberate, frozen migration, not an automatic nightly action.
3. **Anomaly sweep.** Flag suspicious accounts for review (no money moved).

Everything here calls the already-tested Phase 3/7/8 services; this is schedule +
plumbing.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .. import clock
from ..models.bucket_contest import BucketContest
from ..models.bucketing import AuditEvent, MarketState
from ..services.bucketing import index as ix
from ..services.bucketing import markets as mk
from ..services.bucketing import monitoring, promotion, reference, state

log = structlog.get_logger(__name__)

# Below this many placed players a market has no self-made reference — it waits
# for public seeding or more players (its buckets stay unavailable until then).
_MIN_POPULATION_FOR_SELF_REFERENCE = 20


@dataclass
class BucketingNightlyReport:
    references_created: int = 0
    promotion_advices: int = 0
    anomalies_flagged: int = 0
    markets: list[str] = field(default_factory=list)


async def _population(
    session: AsyncSession, market: mk.BucketMarket
) -> list[MarketState]:
    return list(
        await session.scalars(
            select(MarketState).where(
                MarketState.game == market.game,
                MarketState.mode == market.mode,
                MarketState.metric == market.metric,
                MarketState.n_samples > 0,
            )
        )
    )


async def ensure_references(
    sm: async_sessionmaker[AsyncSession], report: BucketingNightlyReport
) -> None:
    for market in mk.all_markets():
        async with sm() as session:
            active = await state.get_active_reference(
                session, market.game, market.mode, market.metric
            )
            if active is not None:
                continue
            pop = await _population(session, market)
            if len(pop) < _MIN_POPULATION_FOR_SELF_REFERENCE:
                continue
            ref = reference.build_reference(
                [p.index_value for p in pop],
                lower_is_better=market.lower_is_better,
                source="ours",
            )
            await state.activate_reference(
                session, ref, market.game, market.mode, market.metric,
                season=1, version=1,
            )
            # Bucket the players already ingested: they were indexed before a
            # reference existed (bucket = None), so without this they couldn't be
            # placed until their next match. First placement has no hysteresis.
            cuts = list(ref.cuts)
            for p in pop:
                if cuts:
                    lo = min(p.index_value, cuts[0]) - 1.0
                    hi = max(p.index_value, cuts[-1]) + 1.0
                    p.bucket = reference.assign_with_hysteresis(
                        p.index_value, cuts, None, lo=lo, hi=hi
                    )
                else:
                    p.bucket = 0
                p.bucket_version = 1
            await session.commit()
            report.references_created += 1
            report.markets.append(market.key_str)


async def evaluate_markets(
    sm: async_sessionmaker[AsyncSession],
    now: datetime,
    report: BucketingNightlyReport,
) -> None:
    for market in mk.all_markets():
        async with sm() as session:
            active = await state.get_active_reference(
                session, market.game, market.mode, market.metric
            )
            if active is None:
                continue
            pop = await _population(session, market)
            if len(pop) < _MIN_POPULATION_FOR_SELF_REFERENCE:
                continue

            indices = [p.index_value for p in pop]
            # σ_match: the typical within-player match-to-match spread.
            sigmas = [
                ix.stddev(p.m2, p.n_samples) for p in pop if p.n_samples >= 2
            ]
            sigma_match = statistics.median(sigmas) if sigmas else 0.0
            median_matches = statistics.median([p.n_samples for p in pop])
            since = now - timedelta(days=1)
            daily_entrants = int(
                await session.scalar(
                    select(func.count())
                    .select_from(BucketContest)
                    .where(
                        BucketContest.game == market.game,
                        BucketContest.mode == market.mode,
                        BucketContest.metric == market.metric,
                        BucketContest.created_at >= since,
                    )
                )
                or 0
            )

            ev = promotion.evaluate_market(
                indices,
                current_k=active.k,
                sigma_match=sigma_match,
                median_matches=float(median_matches),
                daily_entrants=float(daily_entrants),
            )
            # Advisory only — record the recommendation; do not re-cut here.
            session.add(
                AuditEvent(
                    event_type="promotion_advice",
                    market=market.key_str,
                    after={
                        "current_k": ev.current_k,
                        "eligible_k": ev.eligible_k,
                        "action": ev.action,
                        "binding_gate": ev.binding_gate,
                    },
                    actor="system",
                )
            )
            await session.commit()
            report.promotion_advices += 1


async def sweep_anomalies(
    sm: async_sessionmaker[AsyncSession], report: BucketingNightlyReport
) -> None:
    for market in mk.all_markets():
        async with sm() as session:
            flags = await monitoring.detect_anomalies(session, market)
            if flags:
                await session.commit()
                report.anomalies_flagged += len(flags)
            else:
                await session.rollback()


async def run_bucketing_nightly(
    sm: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> BucketingNightlyReport:
    now = now or clock.now()
    report = BucketingNightlyReport()
    await ensure_references(sm, report)
    await evaluate_markets(sm, now, report)
    await sweep_anomalies(sm, report)
    log.info("bucketing_nightly.complete", **report.__dict__)
    return report
