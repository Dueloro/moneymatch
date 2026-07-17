"""Pool & tournament fairness math (pure, no I/O — 07-phase-4 · Fairness math).

Every number a player sees or is graded against is derived here from their own
frozen `metric_models` baseline — no static thresholds, no user-chosen numbers,
no odds. Because it's a deterministic function of stored inputs, `room_bar` and
each `personal_bar` re-derive byte-for-byte from the saved snapshots (the audit
replay), and it unit-tests without a DB.

- **Personal bar** (pools): `round_to_increment(μ + k·σ)`, `k = {easy: 0.5,
  medium: 1.0, hard: 1.75}`. Implied clear rate `1 − Φ(k)` (≈31/16/4%) is a
  *disclosed difficulty*, not an odds line.
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


def personal_bar(mu: float, sigma: float, k: float, increment: float) -> float:
    """A player's own clear threshold at difficulty `k`: round(μ + k·σ)."""
    return round_to_increment(mu + k * sigma, increment)


def room_bar(bars: list[float], increment: float) -> float:
    """The room's shared threshold: the rounded mean of members' personal bars."""
    if not bars:
        raise ValueError("room bar needs at least one personal bar")
    return round_to_increment(sum(bars) / len(bars), increment)


def clear_prob(bar: float, mu: float, sigma: float) -> float:
    """Implied probability a player with `(μ, σ)` clears `bar`: 1 − Φ((bar − μ)/σ)."""
    if sigma <= 0:
        return 1.0 if mu >= bar else 0.0
    return 1.0 - normal_cdf((bar - mu) / sigma)


def p_target_for_k(k: float) -> float:
    """The difficulty's design clear rate `1 − Φ(k)` (the composition target)."""
    return 1.0 - normal_cdf(k)


def composition_bounds(p_target: float) -> tuple[float, float]:
    """The fair band for a member's implied clear prob: [p_target/2, min(2p, 0.5)]."""
    return p_target / 2.0, min(2.0 * p_target, 0.5)


def member_fair(bar: float, mu: float, sigma: float, p_target: float) -> bool:
    """Whether one member's implied clear prob vs. `bar` sits in the fair band."""
    lo, hi = composition_bounds(p_target)
    p_i = clear_prob(bar, mu, sigma)
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
) -> bool:
    """Whether a room is fair for **every** member (plus the optional spread cap).

    `members` is a list of `(μ, σ)`. When `bars` / `sigmas` / `spread_cap_sigma`
    are supplied the personal-bar spread cap is also enforced.
    """
    if not all(member_fair(bar, mu, sigma, p_target) for mu, sigma in members):
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
