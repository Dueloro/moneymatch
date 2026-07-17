"""Risk monitoring for the admin surface (09-phase-6 · deliverable 2 · Risk view).

Two halves, both read-only analytics over settled contests + the durable
`risk_flags` trail:

- **Rate drift** — per (game, market/difficulty): offered/accepted/settled counts,
  rake accrued, and **actual vs. expected** rates. Duels should sit near 50%
  (the favorite — higher frozen μ — winning far more often means the pairing or a
  metric `k` is mispriced, or someone is exploiting it; the two look identical
  from here). Pools should track their difficulty `p_target`. A row past the drift
  threshold is flagged `alert`.
- **Flag queue** — unresolved `risk_flags` (the Phase-4 sandbagging detector),
  each actionable with freeze (the user) / clear (the flag). Per the launch-plan
  rule kept verbatim: risk responses adjust **future** formation, never an
  accepted in-flight contest.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.play import Match, MatchPlayer, QueueTicket
from ..models.pools import SoloEntry, SoloPool
from ..models.risk import RiskFlag
from ..models.user import User
from ..models.wallet import PlatformLedgerEntry
from . import fairness, markets

# Only alert with enough settled samples for the rate to mean anything, and only
# when it drifts past this absolute band (tune with data).
RISK_MIN_SAMPLES = 10
RISK_RATE_ALERT_DELTA = 0.20


@dataclass
class RateRow:
    game: str
    market: str
    offered: int
    accepted: int
    settled: int
    expected_rate: float | None
    actual_rate: float | None
    rake_cents: int
    dispute_count: int
    alert: bool


@dataclass
class FlagRow:
    id: uuid.UUID
    user_id: uuid.UUID
    username: str | None
    game: str
    metric: str
    kind: str
    detail: dict
    created_at: object


@dataclass
class RiskView:
    rates: list[RateRow] = field(default_factory=list)
    flags: list[FlagRow] = field(default_factory=list)


def _drift_alert(expected: float | None, actual: float | None, n: int) -> bool:
    if expected is None or actual is None or n < RISK_MIN_SAMPLES:
        return False
    return abs(actual - expected) > RISK_RATE_ALERT_DELTA


async def _match_rates(session: AsyncSession) -> list[RateRow]:
    rows: list[RateRow] = []
    pairs = await session.execute(select(Match.game, Match.market).distinct())
    for game, market in pairs:
        accepted = await session.scalar(
            select(func.count())
            .select_from(Match)
            .where(Match.game == game, Match.market == market)
        )
        offered = await session.scalar(
            select(func.count())
            .select_from(QueueTicket)
            .where(QueueTicket.game == game, QueueTicket.market == market)
        )
        settled_ids = list(
            await session.scalars(
                select(Match.id).where(
                    Match.game == game,
                    Match.market == market,
                    Match.state.in_(("SETTLED", "PUSHED")),
                )
            )
        )
        rake = await session.scalar(
            select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
                PlatformLedgerEntry.account == "platform:rake",
                PlatformLedgerEntry.ref_type == "match",
                PlatformLedgerEntry.ref_id.in_(settled_ids),
            )
        )
        expected, actual = await _favorite_win_rate(session, game, market)
        rows.append(
            RateRow(
                game=game,
                market=market,
                offered=int(offered or 0),
                accepted=int(accepted or 0),
                settled=len(settled_ids),
                expected_rate=expected,
                actual_rate=actual,
                rake_cents=int(rake or 0),
                dispute_count=0,
                alert=_drift_alert(expected, actual, len(settled_ids)),
            )
        )
    return rows


async def _favorite_win_rate(
    session: AsyncSession, game: str, market: str
) -> tuple[float | None, float | None]:
    """For a stat duel: expected 0.5, actual = share of decisive matches the
    higher-μ seat won (fair pairing keeps this near 50%). None for non-stat markets."""
    market_def = markets.get(game, market)
    if market_def is None or market_def.kind != markets.KIND_STAT_RACE:
        return None, None
    metric = market_def.metric
    if metric is None:
        return None, None
    decisive = 0
    favorite_wins = 0
    matches = await session.scalars(
        select(Match).where(
            Match.game == game, Match.market == market, Match.state == "SETTLED"
        )
    )
    for match in matches:
        if match.winner_user_id is None:
            continue
        seats = list(
            await session.scalars(
                select(MatchPlayer).where(MatchPlayer.match_id == match.id)
            )
        )
        mus = {
            s.user_id: (s.baseline_snapshot or {}).get(metric, {}).get("mu")
            for s in seats
        }
        if any(v is None for v in mus.values()) or len(seats) != 2:
            continue
        decisive += 1
        favorite = max(mus, key=lambda uid: mus[uid])
        if match.winner_user_id == favorite:
            favorite_wins += 1
    if decisive == 0:
        return 0.5, None
    return 0.5, favorite_wins / decisive


async def _pool_rates(session: AsyncSession) -> list[RateRow]:
    rows: list[RateRow] = []
    groups = await session.execute(
        select(SoloPool.game, SoloPool.metric, SoloPool.difficulty).distinct()
    )
    for game, metric, difficulty in groups:
        pool_ids = list(
            await session.scalars(
                select(SoloPool.id).where(
                    SoloPool.game == game,
                    SoloPool.metric == metric,
                    SoloPool.difficulty == difficulty,
                )
            )
        )
        settled_pool_ids = list(
            await session.scalars(
                select(SoloPool.id).where(
                    SoloPool.game == game,
                    SoloPool.metric == metric,
                    SoloPool.difficulty == difficulty,
                    SoloPool.state == "SETTLED",
                )
            )
        )
        graded = 0
        cleared = 0
        if settled_pool_ids:
            entries = await session.scalars(
                select(SoloEntry).where(SoloEntry.pool_id.in_(settled_pool_ids))
            )
            for e in entries:
                if e.status in ("CLEARED", "MISSED"):
                    graded += 1
                if e.status == "CLEARED":
                    cleared += 1
        rake = await session.scalar(
            select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
                PlatformLedgerEntry.account == "platform:rake",
                PlatformLedgerEntry.ref_type == "solo_pool",
                PlatformLedgerEntry.ref_id.in_(pool_ids),
            )
        )
        expected = fairness.p_target_for_k(fairness.k_for_difficulty(difficulty))
        actual = (cleared / graded) if graded else None
        rows.append(
            RateRow(
                game=game,
                market=f"{metric}/{difficulty}",
                offered=graded,
                accepted=len(pool_ids),
                settled=len(settled_pool_ids),
                expected_rate=expected,
                actual_rate=actual,
                rake_cents=int(rake or 0),
                dispute_count=0,
                alert=_drift_alert(expected, actual, graded),
            )
        )
    return rows


async def _open_flags(session: AsyncSession) -> list[FlagRow]:
    rows = await session.execute(
        select(RiskFlag, User.username)
        .join(User, User.id == RiskFlag.user_id)
        .where(RiskFlag.resolved.is_(False))
        .order_by(RiskFlag.created_at.desc())
    )
    return [
        FlagRow(
            id=flag.id,
            user_id=flag.user_id,
            username=username,
            game=flag.game,
            metric=flag.metric,
            kind=flag.kind,
            detail=flag.detail,
            created_at=flag.created_at,
        )
        for flag, username in rows
    ]


async def risk_view(session: AsyncSession) -> RiskView:
    view = RiskView()
    view.rates = await _match_rates(session) + await _pool_rates(session)
    view.flags = await _open_flags(session)
    return view


async def clear_flag(session: AsyncSession, flag_id: uuid.UUID) -> RiskFlag | None:
    """Resolve a risk flag (a human clearing a false positive / handled case)."""
    flag = await session.get(RiskFlag, flag_id)
    if flag is None:
        return None
    flag.resolved = True
    await session.flush()
    return flag
