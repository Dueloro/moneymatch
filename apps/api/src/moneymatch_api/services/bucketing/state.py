"""The DB glue tying ingestion → index → bucket (Phases 1–3, integration).

This is the worker's per-match pipeline from `BUCKETING_TECHNICAL_WALKTHROUGH.md`
§3–§5, composed from the pure engines:

    record_match  (Phase 1, ingestion.py)
        └─ update_market_state  (Phase 2 index + Phase 3 assignment, here)

`update_market_state` loads-or-creates the small `market_state` row, folds one
new value through the pure `index.update_index`, then re-buckets the player with
`reference.assign_with_hysteresis` against the market's **active** reference
version, and writes the row back. Nothing here recomputes anything the pure
modules own — it only persists their output.

Reference persistence lives here too: `get_active_reference` reads the one active
version; `activate_reference` performs the atomic swap (old active → false, new →
true) that the partial unique index guarantees can never leave two active.

All of it is DB I/O, so its tests are CI-only (need Postgres). The maths it calls
is already proven by the pure test gates.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...adapters.base import NormGame
from ...models.bucketing import MarketReference, MarketState
from . import index as ix
from . import ingestion
from . import markets as mk
from . import reference as rf


async def get_active_reference(
    session: AsyncSession, game: str, mode: str, metric: str
) -> MarketReference | None:
    """The one active reference version for a market, or None if none is active."""
    return await session.scalar(
        select(MarketReference).where(
            MarketReference.game == game,
            MarketReference.mode == mode,
            MarketReference.metric == metric,
            MarketReference.active.is_(True),
        )
    )


def _reference_view(row: MarketReference | None) -> rf.MarketReference | None:
    """Adapt a DB row to the pure `reference.MarketReference` value object."""
    if row is None:
        return None
    return rf.MarketReference(
        cuts=tuple(row.cuts),
        bars=tuple(row.bars),
        lower_is_better=row.lower_is_better,
        source=row.source,
    )


def _typical_bucket_width(cuts: list[float]) -> float | None:
    """A representative bucket width (median gap between cuts) for the index
    fall-floor. None when there are no interior cuts to measure."""
    if len(cuts) < 1:
        return None
    if len(cuts) == 1:
        return None  # a single cut gives no interior width to measure
    gaps = [b - a for a, b in zip(cuts, cuts[1:], strict=False)]
    gaps.sort()
    return gaps[len(gaps) // 2]


async def get_market_state(
    session: AsyncSession,
    player_id: uuid.UUID,
    game: str,
    mode: str,
    metric: str,
) -> MarketState | None:
    return await session.scalar(
        select(MarketState).where(
            MarketState.player_id == player_id,
            MarketState.game == game,
            MarketState.mode == mode,
            MarketState.metric == metric,
        )
    )


async def update_market_state(
    session: AsyncSession,
    player_id: uuid.UUID,
    market: mk.BucketMarket,
    value: float,
) -> MarketState:
    """Fold one new metric `value` into the player's `market_state` for `market`.

    Loads-or-creates the row, applies the pure index update (respecting the
    market's direction + floor, and the fall-floor from the active reference's
    bucket width), then re-buckets under hysteresis against the active reference.
    """
    row = await get_market_state(
        session, player_id, market.game, market.mode, market.metric
    )
    if row is None:
        row = MarketState(
            player_id=player_id,
            game=market.game,
            mode=market.mode,
            metric=market.metric,
        )
        session.add(row)

    ref_row = await get_active_reference(
        session, market.game, market.mode, market.metric
    )
    ref_view = _reference_view(ref_row)
    fall_width = (
        _typical_bucket_width(list(ref_row.cuts)) if ref_row is not None else None
    )

    # Rebuild the immutable IndexState from the row, fold in the value.
    state = ix.IndexState(
        mean=row.mean,
        m2=row.m2,
        n_samples=row.n_samples,
        window=tuple(row.window or ()),
        index_value=row.index_value,
        index_confidence=row.index_confidence,
        peak_goodness=(
            row.peak_goodness if row.peak_goodness is not None else float("-inf")
        ),
    )
    state = ix.update_index(
        state,
        value,
        lower_is_better=market.lower_is_better,
        metric_floor=market.floor,
        fall_floor_bucket_width=fall_width,
    )

    # Persist Welford + index.
    row.mean = state.mean
    row.m2 = state.m2
    row.n_samples = state.n_samples
    row.window = list(state.window)
    row.index_value = state.index_value
    row.index_confidence = state.index_confidence
    row.peak_goodness = (
        None if state.peak_goodness == float("-inf") else state.peak_goodness
    )

    # Re-bucket under hysteresis against the active reference (if any).
    if ref_view is not None and ref_view.cuts:
        cuts = list(ref_view.cuts)
        lo = min(state.index_value, cuts[0]) - 1.0
        hi = max(state.index_value, cuts[-1]) + 1.0
        new_bucket = rf.assign_with_hysteresis(
            state.index_value, cuts, row.bucket, lo=lo, hi=hi
        )
        row.bucket = new_bucket
        row.bucket_version = ref_row.version
    # provisional flips off once the market has enough graded samples.
    from .placement import is_provisional

    row.provisional = is_provisional(state.n_samples)

    await session.flush()
    return row


async def record_and_update(
    session: AsyncSession,
    player_id: uuid.UUID,
    game: str,
    norm: NormGame,
) -> bool:
    """The worker's per-match entry point: record the match once, then update the
    player's `market_state` for every metric that this match carries for its
    market. Returns whether a new match row was written.

    Only updates indices when the match was *newly* recorded (idempotency: a
    re-seen match must not fold the same value into the index twice).
    """
    mode = ingestion.bucket_mode_for(game, norm)
    if mode is None:
        return False

    newly = await ingestion.record_match(session, player_id, game, norm, mode=mode)
    if not newly:
        return False

    for market in mk.for_game(game):
        if market.mode != mode:
            continue
        if market.metric not in norm.metrics:
            continue
        await update_market_state(
            session, player_id, market, norm.metrics[market.metric]
        )
    return True


async def activate_reference(
    session: AsyncSession,
    ref: rf.MarketReference,
    game: str,
    mode: str,
    metric: str,
    *,
    season: int = 1,
    version: int,
) -> MarketReference:
    """Insert a new reference version and make it the sole active one, atomically.

    Deactivates any currently-active version *first* (so the partial unique index
    on `active` is never violated mid-swap), then inserts/activates the new one.
    """
    await session.execute(
        update(MarketReference)
        .where(
            MarketReference.game == game,
            MarketReference.mode == mode,
            MarketReference.metric == metric,
            MarketReference.active.is_(True),
        )
        .values(active=False)
    )
    row = MarketReference(
        game=game,
        mode=mode,
        metric=metric,
        season=season,
        version=version,
        cuts=list(ref.cuts),
        bars=list(ref.bars),
        k=ref.k,
        lower_is_better=ref.lower_is_better,
        source=ref.source,
        active=True,
    )
    session.add(row)
    await session.flush()
    return row
