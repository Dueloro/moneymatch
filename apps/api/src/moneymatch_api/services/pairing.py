"""Duel-forecast pairing math (pure, no I/O — launch-plan §4.5(d)).

The fairness engine for head-to-head pairing. Because equal stakes forbid
handicaps, the only lever for a fair contest is **who plays whom**, so we hold
each pairing near a 50/50 forecast:

- **Stat duels** model each player's next-match stat as an independent normal
  from their `metric_models` row, giving
  ``P(a beats b) = Φ((μa − μb) / √(σa² + σb²))``; a pair is *eligible* only if
  that probability sits inside ``[0.5 − w, 0.5 + w]``.
- **Chess `win_h2h`** uses the Elo rating band instead (Elo already *is* the
  forecast — `services/skill_rating.py`).
- ``w`` **widens with wait time** along a configured ladder (queue-depth aware
  in the service); past the last stage we stop auto-widening and the UI offers
  keep-waiting / cancel-refund.
- Among eligible candidates we pick the **lowest composite score** — mean gap,
  rating distance, and a variance term that avoids pairing a steady player with
  a boom-or-bust one.

Everything here is a deterministic function of numbers so it unit-tests without a
DB; the matchmaking service supplies the numbers from frozen baselines.
"""

from __future__ import annotations

import math

from ..constants import (
    CHESS_BAND_GROWTH_PER_SEC,
    CHESS_BASE_BAND,
    CHESS_MAX_BAND,
    PAIRING_WIDENING_LADDER,
    SELECT_W_MEAN_GAP,
    SELECT_W_RATING,
    SELECT_W_VARIANCE,
)

# Elo scale used to normalize a rating gap into the composite score's 0..~1 term.
_RATING_NORM_SCALE = 400.0

Ladder = tuple[tuple[int, float], ...]


def normal_cdf(z: float) -> float:
    """Φ(z) — standard-normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def forecast_prob(mu_a: float, sigma_a: float, mu_b: float, sigma_b: float) -> float:
    """``P(a beats b) = Φ((μa − μb) / √(σa² + σb²))`` for higher-is-better stats.

    With both variances zero the outcome is deterministic: equal means → 0.50,
    otherwise the higher mean wins outright (1.0 / 0.0).
    """
    denom = math.sqrt(sigma_a * sigma_a + sigma_b * sigma_b)
    if denom == 0.0:
        if mu_a == mu_b:
            return 0.5
        return 1.0 if mu_a > mu_b else 0.0
    return normal_cdf((mu_a - mu_b) / denom)


def band_width_for_age(
    age_seconds: float, ladder: Ladder = PAIRING_WIDENING_LADDER
) -> float:
    """The eligibility half-width ``w`` a ticket has reached at ``age_seconds``.

    Steps up through the ladder; past the last stage it stays at the widest
    configured ``w`` (the service, not the math, decides to stop auto-pairing).
    """
    w = ladder[0][1]
    for max_age, stage_w in ladder:
        w = stage_w
        if age_seconds <= max_age:
            return w
    return w


def tolerance_stage_for_age(
    age_seconds: float, ladder: Ladder = PAIRING_WIDENING_LADDER
) -> int:
    """0-based ladder stage index a ticket has reached (for telemetry/storage)."""
    stage = 0
    for i, (max_age, _w) in enumerate(ladder):
        stage = i
        if age_seconds <= max_age:
            return stage
    return stage


def is_widening_exhausted(
    age_seconds: float, ladder: Ladder = PAIRING_WIDENING_LADDER
) -> bool:
    """True once a ticket has aged past the last ladder stage (offer cancel)."""
    return age_seconds > ladder[-1][0]


def effective_w(
    age_a: float, age_b: float, ladder: Ladder = PAIRING_WIDENING_LADDER
) -> float:
    """The band two tickets pair within: the wider of their two ladders (PoC rule)."""
    return max(band_width_for_age(age_a, ladder), band_width_for_age(age_b, ladder))


def is_forecast_eligible(prob: float, w: float) -> bool:
    """Whether ``P(a beats b)`` sits inside the fair window ``[0.5 − w, 0.5 + w]``."""
    return 0.5 - w <= prob <= 0.5 + w


def chess_band(age_seconds: float) -> int:
    """Elo half-band a chess ticket searches within at ``age_seconds`` (PoC ladder)."""
    return int(
        min(CHESS_MAX_BAND, CHESS_BASE_BAND + age_seconds * CHESS_BAND_GROWTH_PER_SEC)
    )


def effective_chess_band(age_a: float, age_b: float) -> int:
    """The Elo band two chess tickets pair within (wider of the two)."""
    return max(chess_band(age_a), chess_band(age_b))


def is_chess_eligible(rating_a: int, rating_b: int, band: int) -> bool:
    """Whether two chess ratings sit within the current Elo band."""
    return abs(rating_a - rating_b) <= band


def _sigma_pooled(sigma_a: float, sigma_b: float) -> float:
    pooled = math.sqrt((sigma_a * sigma_a + sigma_b * sigma_b) / 2.0)
    # Degenerate (both zero variance): avoid div-by-zero; means carry the score.
    return pooled or 1.0


def composite_score(
    mu_a: float,
    sigma_a: float,
    mu_b: float,
    sigma_b: float,
    *,
    rating_a: int | None = None,
    rating_b: int | None = None,
) -> float:
    """Lower is a better pairing. Blends mean gap, rating distance, and a variance
    term (steadiness match) per the launch-plan weights (06-phase-3 · deliverable 2).
    """
    pooled = _sigma_pooled(sigma_a, sigma_b)
    mean_term = abs(mu_a - mu_b) / pooled
    var_term = abs(sigma_a - sigma_b) / pooled
    if rating_a is not None and rating_b is not None:
        rating_term = abs(rating_a - rating_b) / _RATING_NORM_SCALE
    else:
        rating_term = 0.0
    return (
        SELECT_W_MEAN_GAP * mean_term
        + SELECT_W_RATING * rating_term
        + SELECT_W_VARIANCE * var_term
    )
