"""Pool & tournament fairness math (pure, no I/O — 07-phase-4 · Fairness math).

Every number a player sees or is graded against is derived here from their own
frozen `metric_models` baseline — no static thresholds, no user-chosen numbers,
no odds. Because it's a deterministic function of stored inputs, `room_bar` and
each `personal_bar` re-derive byte-for-byte from the saved snapshots (the audit
replay), and it unit-tests without a DB.

- **Personal bar** (pools): `round_to_increment(μ + k·σ)`, with `k` taken from
  `constants.POOL_DIFFICULTY_K` — **the single source of truth; this docstring
  deliberately does not restate the values.** Implied clear rate `1 − Φ(k)` is a
  *disclosed difficulty*, not an odds line.

  (This paragraph used to inline a stale copy of those values, so anyone reading
  the file to understand the difficulty tiers got the wrong numbers.
  `test_docs_do_not_drift.py` now fails if any copy is reintroduced here — the
  fix is not to keep two copies in sync, it is to refuse to have two.)
- **Room bar**: `round_to_increment(mean(personal_bars))`.
- **Room composition**: a room forms only if every member's implied clear
  probability vs. the room bar, `p_i = 1 − Φ((room_bar − μi)/σi)`, sits in
  `[p_target/2, min(2·p_target, 0.5)]` — a shark can't drag the average to
  trivial-for-them, an outlier can't be dragged up — plus a personal-bar spread
  cap.
- **Tournament fields**: a μ-dispersion cap `max(μ) − min(μ) ≤ cap · σ_pooled`.
- **Scoring**: mean of the metric over the first N qualifying matches.
"""

from __future__ import annotations

import math

from ..constants import POOL_DIFFICULTY_K
from .pairing import normal_cdf


def round_to_increment(value: float, increment: float) -> float:
    """Round `value` to the nearest `increment`, deterministically.

    Rounded to 6 decimals so repeated derivations from the same inputs produce
    the identical float (the room-bar reproducibility guarantee).
    """
    if increment <= 0:
        return round(value, 6)
    return round(round(value / increment) * increment, 6)


# A bar quoted in whole units (moves, kills) cannot express difficulty at
# sub-unit resolution. With a tight spread every tier rounds to the same number
# and the three difficulties become one card printed three times, so the spread
# used to *place* the bar has a floor relative to the quoting increment. The
# disclosed clear rate is still computed from the player's real spread, so the
# number on the card stays honest.
# The tightest gap between tiers is easy -> medium, at (1.0 - 0.5) = 0.5 of the
# spread. Two increments of spread makes that gap a full increment, which
# survives rounding, so the three tiers can never collapse onto one number.
_MIN_SIGMA_INCREMENTS = 2.0


def effective_sigma(sigma: float, increment: float) -> float:
    """A usable spread for bar maths, floored relative to the quoting increment.

    Apply this **once**, where a metric model is read, and use the result for
    everything downstream: the bar, the fair band, and the disclosed clear rate.
    Flooring only at bar placement made the bar and the fairness check disagree,
    so a tight-spread player's room could never compose: the bar sat where a
    wide spread would put it while their implied clear probability was computed
    from the narrow one, landing far outside the fair band.

    Two games of similar length produce a spread near zero, which is a small
    sample rather than genuine consistency, so treating it as real is wrong in
    both directions.
    """
    return max(sigma, increment * _MIN_SIGMA_INCREMENTS)


def _lognormal_params(mu: float, sigma: float) -> tuple[float, float]:
    """The (m, s) of the lognormal with this mean and standard deviation."""
    s2 = math.log(1.0 + (sigma * sigma) / (mu * mu))
    return math.log(mu) - s2 / 2.0, math.sqrt(s2)


def personal_bar(
    mu: float,
    sigma: float,
    k: float,
    increment: float,
    lower_is_better: bool = False,
    *,
    positive: bool = False,
    floor: float = 0.0,
) -> float:
    """A player's own clear threshold at difficulty `k`.

    `round(μ + k·σ)` for a stat where more is better, `round(μ − k·σ)` where
    less is (fewest moves). Harder therefore means a bigger number in the first
    case and a smaller one in the second, while the implied clear rate is
    1 − Φ(k) either way.

    `positive` switches to a lognormal, which is the right shape for a quantity
    that cannot be zero or negative and has a long right tail: moves per game,
    match duration, damage. On a normal, `μ − k·σ` walks off the end of the
    scale as soon as the spread approaches the mean, which is how a hard chess
    pool came to ask for **minus six moves**. A lognormal cannot produce a
    non-positive bar at any `k`, and it fits the real left tail better: measured
    against 4,647 Lichess games it was accurate to 1.26 moves versus the
    normal's 1.44, and where the normal predicted a 4%-clear bar of 3.4 moves
    for a 1000-rated player the true figure was 7.

    `floor` is the last line of defence: a hard minimum for the metric (2 moves
    for chess, the fastest possible mate). It should never bind once `positive`
    is set, and exists so that a bar is never *unwinnable by arithmetic*.
    """
    if positive and mu > 0.0 and sigma > 0.0:
        m, s = _lognormal_params(mu, sigma)
        raw = math.exp(m - k * s) if lower_is_better else math.exp(m + k * s)
    else:
        raw = mu + (-k * sigma if lower_is_better else k * sigma)
    return max(floor, round_to_increment(raw, increment))


def room_bar(bars: list[float], increment: float) -> float:
    """The room's shared threshold: the rounded mean of members' personal bars."""
    if not bars:
        raise ValueError("room bar needs at least one personal bar")
    return round_to_increment(sum(bars) / len(bars), increment)


def clear_prob(
    bar: float,
    mu: float,
    sigma: float,
    lower_is_better: bool = False,
    *,
    positive: bool = False,
) -> float:
    """Implied probability a player with `(μ, σ)` clears `bar`.

    `1 − Φ((bar − μ)/σ)` when clearing means reaching the bar, `Φ((bar − μ)/σ)`
    when it means coming in under it.

    `positive` must be passed exactly as it was to `personal_bar`. Placing the
    bar under one distribution and judging it under another is not a rounding
    difference, it is two different answers to the same question: a room whose
    bar sat where a lognormal put it, scored against a normal, computes clear
    probabilities outside the fair band and can never form.
    """
    if sigma <= 0 or mu <= 0 and positive:
        cleared = mu <= bar if lower_is_better else mu >= bar
        return 1.0 if cleared else 0.0
    if positive:
        if bar <= 0:
            return 1.0 if not lower_is_better else 0.0
        m, s = _lognormal_params(mu, sigma)
        z = (math.log(bar) - m) / s
    else:
        z = (bar - mu) / sigma
    return normal_cdf(z) if lower_is_better else 1.0 - normal_cdf(z)


def p_target_for_k(k: float) -> float:
    """The difficulty's design clear rate `1 − Φ(k)` (the composition target)."""
    return 1.0 - normal_cdf(k)


def composition_bounds(p_target: float) -> tuple[float, float]:
    """The fair band for a member's implied clear prob: [p_target/2, min(2p, 0.5)]."""
    return p_target / 2.0, min(2.0 * p_target, 0.5)


def member_fair(
    bar: float,
    mu: float,
    sigma: float,
    p_target: float,
    lower_is_better: bool = False,
    *,
    positive: bool = False,
) -> bool:
    """Whether one member's implied clear prob vs. `bar` sits in the fair band."""
    lo, hi = composition_bounds(p_target)
    p_i = clear_prob(bar, mu, sigma, lower_is_better, positive=positive)
    return lo <= p_i <= hi


def pooled_sigma(sigmas: list[float]) -> float:
    """RMS of the members' σ — the shared scale for spread/dispersion caps."""
    if not sigmas:
        return 0.0
    return math.sqrt(sum(s * s for s in sigmas) / len(sigmas))


def spread_ok(bars: list[float], sigmas: list[float], cap_sigma: float) -> bool:
    """Personal-bar spread cap: max − min bar ≤ cap · σ_pooled."""
    if len(bars) < 2:
        return True
    scale = pooled_sigma(sigmas)
    if scale <= 0:
        return max(bars) == min(bars)  # zero variance ⇒ bars must coincide
    return (max(bars) - min(bars)) <= cap_sigma * scale


def composition_ok(
    bar: float,
    members: list[tuple[float, float]],
    p_target: float,
    *,
    sigmas: list[float] | None = None,
    spread_cap_sigma: float | None = None,
    bars: list[float] | None = None,
    lower_is_better: bool = False,
    positive: bool = False,
) -> bool:
    """Whether a room is fair for **every** member (plus the optional spread cap).

    `members` is a list of `(μ, σ)`. When `bars` / `sigmas` / `spread_cap_sigma`
    are supplied the personal-bar spread cap is also enforced. `positive` must
    match what the bars were placed with (see `clear_prob`).
    """
    if not all(
        member_fair(bar, mu, sigma, p_target, lower_is_better, positive=positive)
        for mu, sigma in members
    ):
        return False
    if bars is not None and sigmas is not None and spread_cap_sigma is not None:
        return spread_ok(bars, sigmas, spread_cap_sigma)
    return True


def dispersion_ok(mus: list[float], sigmas: list[float], cap: float) -> bool:
    """Tournament μ-dispersion cap: max(μ) − min(μ) ≤ cap · σ_pooled."""
    if len(mus) < 2:
        return True
    scale = pooled_sigma(sigmas)
    if scale <= 0:
        return max(mus) == min(mus)
    return (max(mus) - min(mus)) <= cap * scale


def first_n_average(values: list[float], n: int) -> tuple[float | None, int]:
    """Mean of the first `n` values (chronological). Returns (avg, count_used).

    First-N, not best-of: extra games buy zero extra chances. `(None, 0)` when
    there are no qualifying values (a zero-match entrant forfeits, ranked last).
    """
    used = values[:n]
    if not used:
        return None, 0
    return sum(used) / len(used), len(used)


def k_for_difficulty(difficulty: str) -> float:
    """The `k` multiplier for a pool difficulty (easy/medium/hard)."""
    return POOL_DIFFICULTY_K[difficulty]
