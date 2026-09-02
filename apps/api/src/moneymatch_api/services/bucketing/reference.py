"""Phase 3 — reference distributions, bucket cuts & assignment.

Pure, deterministic, no DB. Given a population of skill indices for one market,
draw K buckets (cut points) so that within-bucket variance is minimised, then
place any index into a bucket with a single `searchsorted`, with hysteresis so a
player hovering on a boundary doesn't flip every match.

Two hard requirements from `IMPLEMENTATION_BUCKETING.md` Phase 3:

1. **Reproducible.** The same index against the same reference lands in the same
   bucket *every* call. So the cut algorithm is 1-D dynamic programming
   (Fisher-Jenks / min-within-variance), **never** a randomised clusterer like
   k-means with a random seed. Same input list → same cuts, bit for bit.
2. **Doesn't flap.** Assignment uses hysteresis: a player only moves buckets once
   their index crosses the boundary by a margin, and never drops more than one
   bucket at once.

All maths is on the **index in value space**; direction (higher/lower is better)
does not matter to cutting — a bucket is just a contiguous band of the skill
line, and "better" only decides which end is the top bucket, which the caller
labels. Cut points are always ascending in value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Launch K (justified in Phase 7 — three bands is right until a market grows).
DEFAULT_K = 3
# Hysteresis margin as a fraction of the bucket width the player would move into.
HYSTERESIS_MARGIN_FRAC = 0.15
# Bar-per-bucket = bucket median + this fraction of the bucket width as a margin.
BAR_MARGIN_FRAC = 0.0  # bars are the bucket median by default; caller may raise


# --------------------------------------------------------------------------- #
# Cut computation
# --------------------------------------------------------------------------- #


def _prefix_sums(values: list[float]) -> tuple[list[float], list[float]]:
    """Prefix sums of x and x² for O(1) segment variance."""
    n = len(values)
    p1 = [0.0] * (n + 1)
    p2 = [0.0] * (n + 1)
    for i, v in enumerate(values):
        p1[i + 1] = p1[i] + v
        p2[i + 1] = p2[i] + v * v
    return p1, p2


def _segment_ssd(p1: list[float], p2: list[float], i: int, j: int) -> float:
    """Sum of squared deviations for the sorted slice [i, j) — O(1)."""
    count = j - i
    if count <= 1:
        return 0.0
    s = p1[j] - p1[i]
    sq = p2[j] - p2[i]
    return sq - s * s / count


def fisher_jenks_breaks(values: list[float], k: int) -> list[float]:
    """K−1 ascending cut points that minimise total within-bucket variance.

    Exact 1-D DP (Fisher-Jenks). Deterministic: no randomness, no seed. Returns
    the cut *values* (upper edge of each bucket except the last). With fewer
    distinct values than `k`, returns as many meaningful cuts as exist (buckets
    beyond the data are empty but the scheme stays valid).
    """
    if k <= 1:
        return []
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        return []
    k = min(k, n)
    if k == 1:
        return []

    p1, p2 = _prefix_sums(xs)
    # cost[m][i] = min SSD partitioning xs[0:i] into m buckets.
    inf = math.inf
    cost = [[inf] * (n + 1) for _ in range(k + 1)]
    arg = [[0] * (n + 1) for _ in range(k + 1)]
    cost[0][0] = 0.0
    for m in range(1, k + 1):
        for i in range(m, n + 1):
            best = inf
            best_j = m - 1
            # last bucket is xs[j:i]; previous m-1 buckets cover xs[0:j].
            for j in range(m - 1, i):
                if cost[m - 1][j] == inf:
                    continue
                c = cost[m - 1][j] + _segment_ssd(p1, p2, j, i)
                if c < best:
                    best = c
                    best_j = j
            cost[m][i] = best
            arg[m][i] = best_j

    # Backtrack the bucket boundaries (indices into xs).
    bounds: list[int] = []
    i = n
    for m in range(k, 0, -1):
        j = arg[m][i]
        if m > 1:
            bounds.append(j)
        i = j
    bounds.reverse()
    # A cut value sits between the top of one bucket and the bottom of the next;
    # place it at the midpoint so a value exactly on a data point is unambiguous.
    # Only keep a cut that falls between two **distinct** values — a boundary
    # inside a run of identical indices (xs[b-1] == xs[b]) is not a real divider
    # and would empty a bucket (its midpoint equals the value, and assignment
    # promotes on `>=`). Dropping it collapses K to what the data can support.
    return [
        (xs[b - 1] + xs[b]) / 2.0
        for b in bounds
        if 0 < b < n and xs[b - 1] < xs[b]
    ]


def quantile_breaks(values: list[float], k: int) -> list[float]:
    """Equal-population cut points — the fallback when a market is too small for
    the variance floor to be met. Guarantees every bucket can fill."""
    if k <= 1:
        return []
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        return []
    k = min(k, n)
    out: list[float] = []
    for m in range(1, k):
        idx = m * n / k
        lo = int(math.floor(idx - 0.5))
        lo = max(0, min(lo, n - 2))
        # Only a genuine gap between two distinct values is a valid cut; a
        # boundary inside a run of identical values would empty a bucket.
        if xs[lo] < xs[lo + 1]:
            cut = (xs[lo] + xs[lo + 1]) / 2.0
            if not out or cut > out[-1]:  # strictly ascending, no dupes
                out.append(cut)
    return out


def compute_cuts(
    values: list[float],
    k: int = DEFAULT_K,
    *,
    min_bucket_pop: int = 1,
) -> list[float]:
    """The production cut chooser: minimum-within-variance with a per-bucket
    population floor, falling back to equal-population quantiles when the floor
    can't be met (so no bucket is born empty in a small market).

    Fairness of one-bar-per-bucket depends on buckets being skill-tight, which is
    what Fisher-Jenks buys; the quantile fallback trades a little tightness for a
    guarantee that every bucket fills.
    """
    if k <= 1 or len(values) == 0:
        return []
    cuts = fisher_jenks_breaks(values, k)
    if _min_population(values, cuts) >= min_bucket_pop:
        return cuts
    return quantile_breaks(values, k)


def _min_population(values: list[float], cuts: list[float]) -> int:
    if not values:
        return 0
    counts = [0] * (len(cuts) + 1)
    for v in values:
        counts[assign_bucket(v, cuts)] += 1
    return min(counts)


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #


def assign_bucket(index_value: float, cuts: list[float]) -> int:
    """Bucket = number of cut points strictly below the index. O(log K).

    Boundary rule (documented and tested): a value **exactly on a cut** goes to
    the **higher** bucket (`>=` promotes), so `bucket ∈ [0, len(cuts)]`.
    """
    lo, hi = 0, len(cuts)
    while lo < hi:
        mid = (lo + hi) // 2
        if index_value >= cuts[mid]:
            lo = mid + 1
        else:
            hi = mid
    return lo


def bucket_width(cuts: list[float], bucket: int, *, lo: float, hi: float) -> float:
    """Width of a bucket's value band, using the market's `lo`/`hi` support for
    the two open-ended end buckets."""
    left = lo if bucket == 0 else cuts[bucket - 1]
    right = hi if bucket == len(cuts) else cuts[bucket]
    return max(right - left, 0.0)


def assign_with_hysteresis(
    index_value: float,
    cuts: list[float],
    current_bucket: int | None,
    *,
    lo: float,
    hi: float,
    margin_frac: float = HYSTERESIS_MARGIN_FRAC,
) -> int:
    """Bucket for `index_value`, debounced against `current_bucket`.

    - No current bucket (first placement) → the raw assignment.
    - Otherwise only move if the index has crossed the boundary **into the new
      bucket by `margin_frac` of that bucket's width**, and never drop more than
      one bucket in a single step (a bad night can cost at most one rank).
    """
    raw = assign_bucket(index_value, cuts)
    if current_bucket is None:
        return raw
    if raw == current_bucket:
        return current_bucket

    if raw > current_bucket:
        # Moving up: require clearing the boundary into `current+1` by the margin.
        target = current_bucket + 1
        boundary = cuts[current_bucket]  # upper edge of current bucket
        width = bucket_width(cuts, target, lo=lo, hi=hi)
        if index_value >= boundary + margin_frac * width:
            return target  # step up at most one bucket
        return current_bucket
    else:
        # Moving down: require dropping below the lower edge by the margin, and
        # step down at most one bucket.
        target = current_bucket - 1
        boundary = cuts[current_bucket - 1]  # lower edge of current bucket
        width = bucket_width(cuts, target, lo=lo, hi=hi)
        if index_value <= boundary - margin_frac * width:
            return target
        return current_bucket


# --------------------------------------------------------------------------- #
# Bars — one per bucket
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MarketReference:
    """A versioned, seasoned reference for one market: the cut points and the one
    bar per bucket. Serialises 1:1 to a `market_reference` row."""

    cuts: tuple[float, ...]
    bars: tuple[float, ...]
    lower_is_better: bool = False
    source: str = "public"

    @property
    def k(self) -> int:
        return len(self.cuts) + 1

    def bucket_of(self, index_value: float) -> int:
        return assign_bucket(index_value, list(self.cuts))

    def bar_for(self, bucket: int) -> float:
        return self.bars[bucket]


def bars_from_population(
    values: list[float],
    cuts: list[float],
    *,
    lower_is_better: bool = False,
    margin_frac: float = BAR_MARGIN_FRAC,
) -> list[float]:
    """One bar per bucket = the bucket's median nudged by a margin **toward the
    harder end** (so the bar is a touch above median for higher-is-better, a
    touch below for lower-is-better). Buckets with no members fall back to the
    midpoint of their band.
    """
    xs = sorted(values)
    k = len(cuts) + 1
    members: list[list[float]] = [[] for _ in range(k)]
    for v in xs:
        members[assign_bucket(v, cuts)].append(v)

    bars: list[float] = []
    for b in range(k):
        band = members[b]
        if band:
            med = _median(band)
            width = (max(band) - min(band)) or 0.0
            nudge = margin_frac * width
            bars.append(med + nudge if not lower_is_better else med - nudge)
        else:
            # Empty bucket: use the midpoint of its cut band as a placeholder.
            left = cuts[b - 1] if b > 0 else (xs[0] if xs else 0.0)
            right = cuts[b] if b < len(cuts) else (xs[-1] if xs else 0.0)
            bars.append((left + right) / 2.0)
    return bars


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def build_reference(
    values: list[float],
    k: int = DEFAULT_K,
    *,
    lower_is_better: bool = False,
    min_bucket_pop: int = 1,
    source: str = "public",
) -> MarketReference:
    """End-to-end: population → cuts → bars → a `MarketReference`."""
    cuts = compute_cuts(values, k, min_bucket_pop=min_bucket_pop)
    bars = bars_from_population(values, cuts, lower_is_better=lower_is_better)
    return MarketReference(
        cuts=tuple(cuts),
        bars=tuple(bars),
        lower_is_better=lower_is_better,
        source=source,
    )
