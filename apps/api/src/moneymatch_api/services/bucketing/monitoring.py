"""Phase 8 — monitoring, the anomaly watchdog & the ML corpus.

Three things, all read-mostly:

1. **The per-market rollup** (`market_health`) — the four numbers the deep-dive
   says drive everything: rated players (N), median matches per player (n),
   per-bucket population/fill, and boundary wobble. These feed the promote/demote
   decision and an ops dashboard where a starving bucket shows up early.

2. **The anomaly watchdog** (`detect_anomalies`) — flags accounts whose index
   looks bought/boosted (an elite index off very few games), routing them to a
   **stake hold + human review**, never an automatic ban. Improvement and cheating
   look identical to the maths; only a person can tell them apart, so this only
   *detects*. The rating itself stays best-of.

3. **The ML corpus export** (`export_corpus`) — `match_stats` read at rest as a
   pseudonymous, point-in-time training set: full stat vectors keyed by the
   internal `player_id`, labelled with the outcome, and — by construction — no
   external handle or PII (that lives in other tables). ML is for learning index
   weights / playstyle hints / fraud, never the bucketing itself.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.bucketing import AuditEvent, MarketState, MatchStat
from . import config as cfg
from . import markets as mk

# Anomaly heuristic: an index in the market's top fraction reached on fewer than
# this many samples is suspicious (bought/boosted). Detection only → hold + review.
ANOMALY_MIN_SAMPLES = 10
ANOMALY_TOP_FRACTION = 0.90


@dataclass(frozen=True)
class MarketHealth:
    market: str
    rated_players: int
    median_matches: float
    bucket_population: dict[int, int]
    starving_buckets: list[int]  # buckets that can't currently fill a room


async def market_health(
    session: AsyncSession, market: mk.BucketMarket
) -> MarketHealth:
    """The four monitoring numbers for one market."""
    rows = (
        (
            await session.execute(
                select(MarketState.n_samples, MarketState.bucket).where(
                    MarketState.game == market.game,
                    MarketState.mode == market.mode,
                    MarketState.metric == market.metric,
                    MarketState.n_samples > 0,
                )
            )
        )
        .all()
    )
    n_players = len(rows)
    median_matches = (
        statistics.median([r[0] for r in rows]) if rows else 0.0
    )
    pop: dict[int, int] = {}
    for _n, bucket in rows:
        if bucket is not None:
            pop[bucket] = pop.get(bucket, 0) + 1
    starving = sorted(b for b, c in pop.items() if c < cfg.BUCKET_ROOM_SIZE)
    return MarketHealth(
        market=market.key_str,
        rated_players=n_players,
        median_matches=float(median_matches),
        bucket_population=pop,
        starving_buckets=starving,
    )


@dataclass(frozen=True)
class AnomalyFlag:
    player_id: uuid.UUID
    market: str
    index_value: float
    n_samples: int
    reason: str


async def detect_anomalies(
    session: AsyncSession, market: mk.BucketMarket
) -> list[AnomalyFlag]:
    """Flag suspicious accounts for **review** (never auto-ban).

    Heuristic: an index sitting in the market's top `ANOMALY_TOP_FRACTION` of the
    population but reached on fewer than `ANOMALY_MIN_SAMPLES` games — an elite
    number off almost no play, the shape a boosted/bought account makes. Writes an
    `audit_events` row per flag (actor='system') so the risk queue can pick it up;
    it moves no money and bans no one.
    """
    rows = (
        (
            await session.execute(
                select(
                    MarketState.player_id,
                    MarketState.index_value,
                    MarketState.n_samples,
                ).where(
                    MarketState.game == market.game,
                    MarketState.mode == market.mode,
                    MarketState.metric == market.metric,
                    MarketState.n_samples > 0,
                )
            )
        )
        .all()
    )
    if len(rows) < 5:
        return []  # too small a population to call anything anomalous

    values = sorted(
        (r[1] for r in rows), reverse=not market.lower_is_better
    )
    # The top-fraction threshold, in the "good" direction.
    cut_idx = int((1 - ANOMALY_TOP_FRACTION) * len(values))
    threshold = values[min(cut_idx, len(values) - 1)]

    flags: list[AnomalyFlag] = []
    for player_id, index_value, n in rows:
        if market.lower_is_better:
            in_top = index_value <= threshold
        else:
            in_top = index_value >= threshold
        if in_top and n < ANOMALY_MIN_SAMPLES:
            reason = (
                f"top-decile index {index_value:g} reached on only {n} games "
                "— review for boosting/purchase"
            )
            flags.append(
                AnomalyFlag(
                    player_id=player_id,
                    market=market.key_str,
                    index_value=index_value,
                    n_samples=n,
                    reason=reason,
                )
            )
            session.add(
                AuditEvent(
                    player_id=player_id,
                    event_type="anomaly_flagged",
                    market=market.key_str,
                    after={"index_value": index_value, "n_samples": n},
                    actor="system",
                    reason=reason,
                )
            )
    await session.flush()
    return flags


async def export_corpus(
    session: AsyncSession,
    *,
    game: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """A pseudonymous, point-in-time ML corpus from `match_stats`.

    Each row is a full stat vector keyed by the internal `player_id` (an opaque
    UUID — no handle, no email, no wallet), labelled with the match outcome. This
    is exactly what the log stored in Phase 1, so the export is a straight read.
    """
    q = select(
        MatchStat.player_id,
        MatchStat.game,
        MatchStat.mode,
        MatchStat.created_at_ms,
        MatchStat.won,
        MatchStat.metrics,
    )
    if game is not None:
        q = q.where(MatchStat.game == game)
    q = q.order_by(MatchStat.created_at_ms)
    if limit is not None:
        q = q.limit(limit)
    rows = (await session.execute(q)).all()
    return [
        {
            # An opaque internal id — pseudonymous, joins to nothing user-facing.
            "player_id": str(r[0]),
            "game": r[1],
            "mode": r[2],
            "created_at_ms": r[3],
            "outcome_won": r[4],
            "features": r[5],
        }
        for r in rows
    ]


async def corpus_size(session: AsyncSession, *, game: str | None = None) -> int:
    q = select(func.count()).select_from(MatchStat)
    if game is not None:
        q = q.where(MatchStat.game == game)
    return int(await session.scalar(q) or 0)
