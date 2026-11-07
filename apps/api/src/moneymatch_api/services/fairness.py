"""Pool & tournament fairness math. Because it's a deterministic function of stored
inputs, `room_bar` and each `personal_bar` re-derive byte-for-byte from the saved
snapshots (the audit replay), and it unit-tests without a DB.
"""

from __future__ import annotations

import math

from ..constants import POOL_DIFFICULTY_K


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def round_to_increment(value: float, increment: float) -> float:
    """Round `value` to the nearest `increment`, deterministically."""
    if increment <= 0:
        return round(value, 6)
    return round(round(value / increment) * increment, 6)


# With a tight spread every tier rounds to the same number and the three difficulties
# become one card printed three times, so the spread used to *place* the bar has a floor
# relative to the quoting increment.
_MIN_SIGMA_INCREMENTS = 2.0


def effective_sigma(sigma: float, increment: float) -> float:
    """A usable spread for bar maths, floored relative to the quoting increment."""
    return max(sigma, increment * _MIN_SIGMA_INCREMENTS)


def _lognormal_params(mu: float, sigma: float) -> tuple[float, float]:
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
    """A player's own clear threshold at difficulty `k`."""
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
    """Implied probability a player with `(μ, σ)` clears `bar`."""
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
    """The fair band for a member's implied clear prob: [p_target/2, min]."""
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
        return max(bars) == min(bars)
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
    """Whether a room is fair for **every** member (plus the optional spread cap)."""
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


def k_for_difficulty(difficulty: str) -> float:
    return POOL_DIFFICULTY_K[difficulty]
