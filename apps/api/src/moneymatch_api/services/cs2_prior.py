"""A starting skill estimate for a CS2 player with no history here.

A pool quotes your bar from your own results. A player who has just signed in
through Steam has none, so without a prior they cannot join anything, which is
the worst possible first experience: sign in, then be told to go away.

Steam offers one usable signal: lifetime `total_kills / total_deaths`. Two
things about it are true and both are encoded here rather than glossed:

- **It is cumulative across casual, deathmatch and bot games**, so it is a weak
  proxy for competitive skill. It seeds a prior; it is never shown as a rating,
  and it is replaced by real results as soon as any arrive.
- **Most profiles keep game details private**, so it is usually unavailable.
  That is the common path, not the edge case, and it falls back to a default
  rather than blocking the link.

The spreads are deliberately wide. A prior that is confidently wrong quotes a
bar the player cannot hit; a wide one quotes a soft bar that real results
correct within a few matches.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import CS2_STEAM_METRICS, GAME_CS2_STEAM
from ..models.skill import MetricModel
from .hosts import steam

log = structlog.get_logger(__name__)

#: (mu, sigma) for a player we know nothing about. Roughly an average
#: matchmaking line, with enough spread that a first bar is never harsh.
_DEFAULTS: dict[str, tuple[float, float]] = {
    "cs2_kd_ratio": (1.00, 0.25),
    "cs2_headshot_pct": (45.0, 12.0),
    "cs2_kills": (18.0, 6.0),
}

#: Sample count stamped on a seeded model. Low on purpose: it is a guess, and
#: it should be outweighed by real matches quickly.
PRIOR_N = 3

#: A lifetime K/D outside this range is not a competitive signal, it is a
#: deathmatch or bot-farming artifact, so it is ignored in favour of the
#: default.
_PLAUSIBLE_KD = (0.4, 2.5)


def _derived(kd: float) -> dict[str, tuple[float, float]]:
    """Scale the defaults by how a player's lifetime K/D compares to average.

    Only K/D is measured, so the other two are moved with it rather than
    invented independently: someone who kills more tends to post more kills per
    match, while headshot rate barely tracks it at all.
    """
    ratio = kd / _DEFAULTS["cs2_kd_ratio"][0]
    return {
        "cs2_kd_ratio": (kd, _DEFAULTS["cs2_kd_ratio"][1]),
        # Headshot percentage is close to independent of K/D; nudge it only.
        "cs2_headshot_pct": (
            _DEFAULTS["cs2_headshot_pct"][0] * (1 + (ratio - 1) * 0.15),
            _DEFAULTS["cs2_headshot_pct"][1],
        ),
        "cs2_kills": (
            _DEFAULTS["cs2_kills"][0] * ratio,
            _DEFAULTS["cs2_kills"][1],
        ),
    }


async def seed(
    session: AsyncSession, user_id: uuid.UUID, steam_id: str
) -> dict[str, tuple[float, float]]:
    """Create the CS2 metric models for a newly linked Steam account.

    Idempotent, and never overwrites a model that already carries real results:
    a re-link must not wipe a player's history back to a guess.
    """
    stats = await steam.get_cs2_lifetime_stats(steam_id)
    kd = stats.kd_ratio if stats else None

    if kd is not None and _PLAUSIBLE_KD[0] <= kd <= _PLAUSIBLE_KD[1]:
        values = _derived(kd)
        source = "steam_lifetime"
    else:
        values = dict(_DEFAULTS)
        source = "default" if kd is None else "default_implausible_kd"

    existing = {
        m.metric: m
        for m in await session.scalars(
            select(MetricModel).where(
                MetricModel.user_id == user_id,
                MetricModel.game == GAME_CS2_STEAM,
            )
        )
    }

    for metric in CS2_STEAM_METRICS:
        mu, sigma = values[metric]
        model = existing.get(metric)
        if model is None:
            session.add(
                MetricModel(
                    user_id=user_id,
                    game=GAME_CS2_STEAM,
                    metric=metric,
                    mu=mu,
                    sigma=sigma,
                    n=PRIOR_N,
                )
            )
        elif model.n <= PRIOR_N:
            # Still a prior, so refresh it. Anything larger is real history and
            # is left alone.
            #
            # `n` has to move too. Linking runs a history bootstrap first, and
            # for a game with no stored matches that leaves a zeroed model
            # behind. A model at n=0 reads as provisional and every pool
            # answers "play a match on this stat first", which is exactly the
            # dead end this prior exists to prevent.
            model.mu = mu
            model.sigma = sigma
            model.n = PRIOR_N
    await session.flush()

    log.info(
        "cs2.prior_seeded",
        user_id=str(user_id),
        steam_id=steam_id,
        source=source,
        lifetime_kd=round(kd, 3) if kd is not None else None,
        values={k: round(v[0], 2) for k, v in values.items()},
    )
    return values


__all__ = ["PRIOR_N", "seed"]
