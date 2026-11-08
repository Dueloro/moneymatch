"""What a typical game looks like, before we know much about *you*."""

from __future__ import annotations

from ..models.linked_account import LinkedAccount

_MOVES_INTERCEPT = 16.65
_MOVES_PER_ELO = 0.01013

_MOVES_SIGMA = 11.94

_RATING_FLOOR, _RATING_CEIL = 800.0, 2600.0

_ASSUMED_RATING = 1500.0

PRIOR_WEIGHT = 10.0

_PRIORS: dict[str, tuple[float, float]] = {}


def _chess_moves_prior(rating: float | None) -> tuple[float, float]:
    elo = _ASSUMED_RATING if rating is None else rating
    elo = min(_RATING_CEIL, max(_RATING_FLOOR, elo))
    return _MOVES_INTERCEPT + _MOVES_PER_ELO * elo, _MOVES_SIGMA


def prior_for(metric: str, rating: float | None) -> tuple[float, float] | None:
    """Expected (mean, spread) for `metric` at `rating`, or None if unmeasured."""
    if metric == "chess_moves":
        return _chess_moves_prior(rating)
    return _PRIORS.get(metric)


def shrink(
    mu: float,
    sigma: float,
    n: int,
    prior: tuple[float, float] | None,
    *,
    weight: float = PRIOR_WEIGHT,
) -> tuple[float, float]:
    """Blend a player's own record toward the prior, by how much record there is."""
    n = max(0, int(n))
    if n <= 0:
        return (prior[0], prior[1]) if prior else (mu, sigma)
    if prior is None:
        return mu, sigma

    prior_mu, prior_sigma = prior
    total = n + weight
    blended_mu = (n * mu + weight * prior_mu) / total
    blended_var = (n * sigma**2 + weight * prior_sigma**2) / total
    return blended_mu, blended_var**0.5


def host_rating(link: LinkedAccount) -> float | None:
    """The linked account's rating on its primary speed, from the snapshot."""
    snapshot = link.profile_snapshot or {}
    formats = snapshot.get("formats") or []
    if not formats:
        return None
    primary = snapshot.get("primary_speed")
    chosen = next((f for f in formats if f.get("speed") == primary), None)
    if chosen is None:
        chosen = max(formats, key=lambda f: f.get("games", 0))
    rating = chosen.get("rating")
    return float(rating) if rating is not None else None


__all__ = ["PRIOR_WEIGHT", "host_rating", "prior_for", "shrink"]
