"""Phase 2 — the skill index (best-of-40%, Welford, rise-fast / fall-slow).

Pure arithmetic, no DB, no clock. One match value in → one updated `IndexState`
out. This is deliberately I/O-free so the money-critical maths is exhaustively
unit-testable (see `tests/test_bucketing_index.py`) and byte-for-byte
deterministic across runs and machines — the settlement path depends on it.

The one idea to hold: a player's index is the **mean of the best 40% of their
last 20 results**, then damped so it rises instantly on improvement but falls
only slowly. A thrown game is never in your best 40%, so deliberately losing to
drop your rank (sandbagging) can't move the number — the defence is structural,
not a detector. See `docs/implementation-guide/IMPLEMENTATION_BUCKETING.md`
Phase 2.

### Direction handling (higher-is-better vs lower-is-better)

Some metrics are better when larger (kills, damage, GPM); chess `moves` is better
when smaller. Rather than branch every comparison, we map every value into a
single **goodness** space — `g = value` for higher-is-better, `g = -value` for
lower-is-better — do all of the best-of / damping maths there (where "best" is
always "largest goodness"), then map the final index back to value space. One
sign flip, zero duplicated logic, no direction bug hiding in a `<` vs `>`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Rolling window of the most recent results the index is computed over.
WINDOW_SIZE = 20
# Fraction of the window that counts as "your best". 0.40 = top 40%.
BEST_FRACTION = 0.40
# Never take the best-of over fewer than this many samples — with a tiny window
# the top-40% would be one lucky game, so the floor keeps it honest.
BEST_MIN_K = 3
# Fall-slow damping: on a worse index we move only this fraction of the way down.
FALL_RATE = 0.25


def welford_update(
    mean: float, m2: float, n: int, x: float
) -> tuple[float, float, int]:
    """One online (mean, m2, n) update — O(1), never rescans history.

    `m2` is the sum of squared deviations; `variance()` turns it into a variance.
    Matches a from-scratch batch computation exactly (proven by a property test).
    """
    n1 = n + 1
    delta = x - mean
    mean1 = mean + delta / n1
    m2_1 = m2 + delta * (x - mean1)
    return mean1, m2_1, n1


def variance(m2: float, n: int) -> float:
    """Sample variance from Welford state (0 for n < 2 — undefined, not an error)."""
    if n < 2:
        return 0.0
    return m2 / (n - 1)


def stddev(m2: float, n: int) -> float:
    return math.sqrt(variance(m2, n))


def best_k(window_len: int) -> int:
    """How many of the window's values count as "the best" — `ceil(0.40·len)`,
    never below `BEST_MIN_K`, never above the window itself."""
    if window_len <= 0:
        return 0
    k = math.ceil(BEST_FRACTION * window_len)
    floor = BEST_MIN_K if window_len >= BEST_MIN_K else window_len
    return max(floor, min(k, window_len))


def best_of_goodness(goodness: list[float]) -> float:
    """Mean of the top-`best_k` goodness values. Empty → 0.0."""
    if not goodness:
        return 0.0
    k = best_k(len(goodness))
    top = sorted(goodness, reverse=True)[:k]
    return sum(top) / len(top)


def confidence(sigma: float, n: int, mean: float) -> float:
    """A 0..1 settledness score from the **relative** standard error of the mean.

    Near 0 while the number still swings; → 1 as it settles. Phase 4 reads this
    to gate stakes. The standard error `σ/√n` is divided by the metric's own
    magnitude (`|mean|`) so the score is scale-free — it behaves the same whether
    the metric lives around 1.0 (K/D) or 400 (GPM) — while still separating a
    wildly noisy history (large σ) from a steady one (small σ) at the same `n`:

        confidence = 1 / (1 + (σ/√n)/|mean|)

    - `n < 2`: 0.0 (no spread yet → not settled, regardless of the value).
    - `σ == 0` with `n ≥ 2`: 1.0 (always the same number → maximally settled).
    - `mean ≈ 0`: the denominator is floored at a tiny epsilon so a metric that
      genuinely averages zero can't divide-by-zero; such a player reads as
      unsettled (low confidence), which is the safe default for stake gating.
    """
    if n < 2:
        return 0.0
    if sigma <= 0.0:
        return 1.0
    denom = max(abs(mean), 1e-9)
    relative_std_err = (sigma / math.sqrt(n)) / denom
    return 1.0 / (1.0 + relative_std_err)


@dataclass(frozen=True)
class IndexState:
    """Everything the index needs, per (player, market). Serialises 1:1 to a
    `market_state` row. Immutable — `update_index` returns a new copy."""

    mean: float = 0.0
    m2: float = 0.0
    n_samples: int = 0
    #: The last `WINDOW_SIZE` raw values, oldest-first.
    window: tuple[float, ...] = field(default_factory=tuple)
    #: The damped skill index, in **value space** (what a bucket is cut on).
    index_value: float = 0.0
    index_confidence: float = 0.0
    #: Best index ever reached, in **goodness space** — the fall-slow floor.
    #: Callers may decay this seasonally to realise the "12-month" horizon.
    peak_goodness: float = -math.inf

    @property
    def has_index(self) -> bool:
        return self.n_samples > 0


def _to_goodness(value: float, lower_is_better: bool) -> float:
    return -value if lower_is_better else value


def _from_goodness(goodness: float, lower_is_better: bool) -> float:
    return -goodness if lower_is_better else goodness


def update_index(
    state: IndexState,
    value: float,
    *,
    lower_is_better: bool = False,
    metric_floor: float = 0.0,
    fall_floor_bucket_width: float | None = None,
) -> IndexState:
    """Fold one new match `value` into the index.

    - `lower_is_better`: chess `moves` (fewer is better); everything else False.
    - `metric_floor`: the smallest physically possible value (chess `moves` = 2);
      the input is clamped up to it so a corrupt 0 can't poison the index.
    - `fall_floor_bucket_width`: width of one bucket in value units. When given,
      the index is never damped below its 12-month peak minus one bucket (in
      goodness space) — one bad night, or a deliberate one, can cost at most a
      bucket. `None` disables the floor (useful in isolation tests).

    Returns a new `IndexState`; the input is never mutated (determinism).
    """
    value = max(value, metric_floor)

    mean, m2, n = welford_update(state.mean, state.m2, state.n_samples, value)
    window = (*state.window, value)[-WINDOW_SIZE:]

    goodness = [_to_goodness(v, lower_is_better) for v in window]
    raw_g = best_of_goodness(goodness)

    stored_g = (
        _to_goodness(state.index_value, lower_is_better) if state.has_index else raw_g
    )

    # Rise-fast / fall-slow, entirely in goodness space (larger = better).
    if raw_g >= stored_g:
        new_g = raw_g  # improvement is taken immediately
    else:
        new_g = stored_g + FALL_RATE * (raw_g - stored_g)  # decline is damped

    peak_g = max(state.peak_goodness, raw_g)
    if fall_floor_bucket_width is not None and math.isfinite(peak_g):
        new_g = max(new_g, peak_g - abs(fall_floor_bucket_width))

    return IndexState(
        mean=mean,
        m2=m2,
        n_samples=n,
        window=window,
        index_value=_from_goodness(new_g, lower_is_better),
        index_confidence=confidence(stddev(m2, n), n, mean),
        peak_goodness=peak_g,
    )


def plain_mean_index(window: tuple[float, ...]) -> float:
    """A plain average of the window — **not** used for rating.

    Kept so the sandbag test can run it alongside the real index and show that a
    plain mean visibly collapses under thrown games while best-of-40% does not.
    """
    return sum(window) / len(window) if window else 0.0


def rebuild_index(
    values: list[float],
    *,
    lower_is_better: bool = False,
    metric_floor: float = 0.0,
    fall_floor_bucket_width: float | None = None,
) -> IndexState:
    """Fold a whole history (oldest-first) through `update_index` from empty.

    The canonical way to (re)compute an index from `match_stats` — used by the
    Phase 1 backfill and by tests that assert Welford equals a batch recompute.
    """
    state = IndexState()
    for v in values:
        state = update_index(
            state,
            v,
            lower_is_better=lower_is_better,
            metric_floor=metric_floor,
            fall_floor_bucket_width=fall_floor_bucket_width,
        )
    return state
