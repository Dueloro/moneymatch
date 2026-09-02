"""Phase 7 — auto-promotion / demotion (buckets grow on their own).

`evaluate_market` is a **pure** nightly decision: given a market's live
population, propose the bucket count `K` it can now support. Three ceilings, all
from `IMPLEMENTATION_BUCKETING.md` Phase 7 — the eligible K is the largest that
passes all three:

- **Precision.** The narrowest proposed bucket must be wider than the noise in a
  player's own index: `min_bucket_width > 2 · (σ_match / √median_matches)`. Buckets
  finer than the measurement error would sort players by luck, not skill.
- **Stability.** Bootstrap the proposed cut points; if resampling the population
  moves a cut by more than 10% of a bucket width, the lines aren't real yet.
- **Liquidity.** Every proposed bucket must gather a room most days:
  `daily_entrants / K ≥ BUCKET_ROOM_SIZE`.

Applying a change is a **separate, controlled** step (`apply_recut`, DB): compute
the new versioned reference, activate it atomically (settlement is frozen by the
`bucketing_settlement_paused`-style flag around the call), and re-bucket everyone
under hysteresis. Past contests keep pointing at their old version, so they still
reconstruct — Phase 6 depends on this.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.bucketing import AuditEvent, MarketState
from . import config as cfg
from . import markets as mk
from . import reference as rf
from . import state as stmod

# The three-gate thresholds (Phase 7).
PRECISION_WIDTH_FACTOR = 2.0
STABILITY_MAX_WOBBLE_FRAC = 0.10
STABILITY_BOOTSTRAP_ROUNDS = 40
# Fisher-Jenks cut computation is O(k·n²); on a large population the nightly job
# would choke re-running it per bootstrap round. So the evaluation works on a
# deterministic downsample of the population — a few hundred points capture the
# distribution's shape, and the bootstrap draws from that. Sampling is seeded, so
# the whole evaluation stays reproducible.
EVAL_SAMPLE_CAP = 200
BOOTSTRAP_SAMPLE_CAP = 120
# K search bounds. K starts at 3 (Phase 3) and grows as the market earns it.
K_MIN = 2
K_MAX = 8


def _downsample(values: list[float], cap: int, *, seed: int) -> list[float]:
    """A deterministic, distribution-preserving subsample of at most `cap`
    points (sorted-stratified: keep every ⌈n/cap⌉-th value after a seeded
    shuffle, so it neither over-weights an order nor drops a mode)."""
    if len(values) <= cap:
        return list(values)
    rng = random.Random(seed)
    idx = list(range(len(values)))
    rng.shuffle(idx)
    return [values[i] for i in sorted(idx[:cap])]


@dataclass(frozen=True)
class GateResult:
    k: int
    precision_ok: bool
    stability_ok: bool
    liquidity_ok: bool

    @property
    def all_ok(self) -> bool:
        return self.precision_ok and self.stability_ok and self.liquidity_ok


@dataclass(frozen=True)
class MarketEvaluation:
    current_k: int
    eligible_k: int
    action: str  # "promote" | "demote" | "hold"
    binding_gate: str | None  # which gate blocked a higher K (None if K_MAX)
    gates: tuple[GateResult, ...]


def _min_bucket_width(indices: list[float], cuts: list[float]) -> float:
    if not indices:
        return 0.0
    lo, hi = min(indices), max(indices)
    edges = [lo, *cuts, hi]
    widths = [b - a for a, b in zip(edges, edges[1:], strict=False)]
    return min(widths) if widths else 0.0


def _precision_ok(
    indices: list[float], cuts: list[float], sigma_match: float, median_matches: float
) -> bool:
    if median_matches <= 0:
        return False
    noise = sigma_match / math.sqrt(median_matches)
    return _min_bucket_width(indices, cuts) > PRECISION_WIDTH_FACTOR * noise


def _stability_ok(
    indices: list[float], cuts: list[float], k: int, *, seed: int = 12345
) -> bool:
    if not cuts:
        return True
    rng = random.Random(seed)
    n = len(indices)
    boot_n = min(n, BOOTSTRAP_SAMPLE_CAP)
    per_cut: list[list[float]] = [[] for _ in cuts]
    for _ in range(STABILITY_BOOTSTRAP_ROUNDS):
        sample = [indices[rng.randrange(n)] for _ in range(boot_n)]
        boot_cuts = rf.compute_cuts(sample, k)
        # Compare position-by-position; a bootstrap that yields fewer cuts (a
        # collapsed bucket) is itself instability.
        if len(boot_cuts) != len(cuts):
            return False
        for i, c in enumerate(boot_cuts):
            per_cut[i].append(c)
    width = _min_bucket_width(indices, cuts)
    if width <= 0:
        return False
    tol = STABILITY_MAX_WOBBLE_FRAC * width
    for samples in per_cut:
        mean = sum(samples) / len(samples)
        sd = math.sqrt(sum((x - mean) ** 2 for x in samples) / len(samples))
        if sd > tol:
            return False
    return True


def _liquidity_ok(daily_entrants: float, k: int) -> bool:
    if k <= 0:
        return False
    return (daily_entrants / k) >= cfg.BUCKET_ROOM_SIZE


def evaluate_market(
    indices: list[float],
    *,
    current_k: int,
    sigma_match: float,
    median_matches: float,
    daily_entrants: float,
) -> MarketEvaluation:
    """Propose the bucket count a market can support, and whether to promote/demote.

    Pure and deterministic (the downsample and stability bootstrap are seeded).
    """
    # Work on a bounded, deterministic subsample so the O(k·n²) cut maths and its
    # bootstrap stay fast on a large market.
    indices = _downsample(indices, EVAL_SAMPLE_CAP, seed=98765)

    gates: list[GateResult] = []
    eligible_k = K_MIN
    binding_gate: str | None = None

    for k in range(K_MIN, K_MAX + 1):
        cuts = rf.compute_cuts(indices, k)
        # If the data can't even yield k−1 real cuts, higher K is impossible.
        precision = _precision_ok(indices, cuts, sigma_match, median_matches)
        stability = _stability_ok(indices, cuts, k)
        liquidity = _liquidity_ok(daily_entrants, k)
        gate = GateResult(k, precision, stability, liquidity)
        gates.append(gate)
        if gate.all_ok and len(cuts) == k - 1:
            eligible_k = k
        elif k > eligible_k:
            # First K that fails — record which gate bound us, then stop climbing.
            if binding_gate is None:
                if not precision:
                    binding_gate = "precision"
                elif not stability:
                    binding_gate = "stability"
                elif not liquidity:
                    binding_gate = "liquidity"
                else:
                    binding_gate = "insufficient_distinct_values"
            break

    if eligible_k > current_k:
        action = "promote"
    elif eligible_k < current_k:
        action = "demote"
    else:
        action = "hold"

    return MarketEvaluation(
        current_k=current_k,
        eligible_k=eligible_k,
        action=action,
        binding_gate=binding_gate,
        gates=tuple(gates),
    )


# --------------------------------------------------------------------------- #
# Controlled re-cut (DB). The caller freezes settlement (a flag) around this.
# --------------------------------------------------------------------------- #


async def _population_indices(
    session: AsyncSession, game: str, mode: str, metric: str
) -> list[float]:
    rows = (
        await session.execute(
            select(MarketState.index_value).where(
                MarketState.game == game,
                MarketState.mode == mode,
                MarketState.metric == metric,
                MarketState.n_samples > 0,
            )
        )
    ).all()
    return [r[0] for r in rows]


async def apply_recut(
    session: AsyncSession,
    market: mk.BucketMarket,
    new_k: int,
    *,
    new_version: int,
    season: int = 1,
    source: str = "ours",
) -> int:
    """Compute a fresh reference at `new_k`, activate it as `new_version`, and
    re-bucket every placed player under hysteresis. Returns the number of players
    re-bucketed. Contests already settled keep their old reference_version.

    The caller must freeze settlement for this market around the call (activate is
    atomic, but a settlement mid-swap should not straddle two versions).
    """
    indices = await _population_indices(
        session, market.game, market.mode, market.metric
    )
    if not indices:
        return 0

    ref = rf.build_reference(
        indices, new_k, lower_is_better=market.lower_is_better, source=source
    )
    await stmod.activate_reference(
        session, ref, market.game, market.mode, market.metric,
        season=season, version=new_version,
    )

    # Re-bucket everyone under hysteresis against the new lines.
    rows = (
        await session.execute(
            select(MarketState).where(
                MarketState.game == market.game,
                MarketState.mode == market.mode,
                MarketState.metric == market.metric,
                MarketState.n_samples > 0,
            )
        )
    ).scalars().all()
    cuts = list(ref.cuts)
    rebucketed = 0
    for row in rows:
        if not cuts:
            new_bucket = 0
        else:
            lo = min(row.index_value, cuts[0]) - 1.0
            hi = max(row.index_value, cuts[-1]) + 1.0
            new_bucket = rf.assign_with_hysteresis(
                row.index_value, cuts, row.bucket, lo=lo, hi=hi
            )
        row.bucket = new_bucket
        row.bucket_version = new_version
        rebucketed += 1

    session.add(
        AuditEvent(
            event_type="market_recut",
            market=market.key_str,
            after={
                "new_version": new_version,
                "new_k": new_k,
                "players_rebucketed": rebucketed,
                "source": source,
            },
        )
    )
    await session.flush()
    return rebucketed
