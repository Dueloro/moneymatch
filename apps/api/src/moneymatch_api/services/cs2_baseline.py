"""What number should a CS2 wager ask you for.

A bar has to be hard enough to be worth winning and close enough to be worth
trying. Quoting it from a single default gets both wrong: a 1.10 K/D bar is
trivial for one player and unreachable for another.

Three sources, blended by how much each is actually worth:

1. **Your own matches.** The only direct evidence, and the only one that
   matters once there is enough of it. Also the noisiest: CS2 is 5v5, so one
   match says as much about your four teammates as about you.
2. **The players you are matched against.** Every resolved match carries nine
   other scoreboards, and Valve put those people in your lobby because it
   thinks they are your level. That is a free, continuously updated read on
   "players around my rank" without asking any ranking API for anything.
3. **A population default**, for a player with no history at all.

The blend is a weighted mean where your own sample earns weight as it grows.
At one match your bar is mostly your lobby's level; by ten it is mostly yours.
The alternative, trusting one match, produces a bar that swings between
"impossible" and "free" depending on how the last game went.

Spread matters as much as the centre, and is deliberately floored. A tight
spread computed from three matches is not consistency, it is a small sample,
and treating it as real quotes a bar nobody can hit.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, replace

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import CS2_STEAM_METRICS, GAME_CS2_STEAM
from ..models.cs2 import Cs2Match
from ..models.skill import MetricModel
from . import cs2_matches
from .hosts import steam

log = structlog.get_logger(__name__)

#: What an average matchmaking player posts, when nothing else is known.
POPULATION: dict[str, tuple[float, float]] = {
    "cs2_kd_ratio": (1.00, 0.28),
    "cs2_headshot_pct": (45.0, 13.0),
    "cs2_kills": (18.0, 6.5),
}

#: Weight each of your own matches carries. Two, so a single real result
#: already outweighs the population guess: the wager is on *your* number, and a
#: player who went 8-19 should not be quoted a bar built from how well the
#: lobby's best player did.
OWN_WEIGHT_PER_MATCH = 2.0

#: Total weight the lobby can ever contribute, before decay. It says what level
#: of player you are matched with, which is useful when we know nothing about
#: you, and should stop mattering once we do.
COHORT_WEIGHT = 2.0

#: How fast the lobby's influence decays as your own record grows. A prior that
#: does not wash out is not a prior, it is a thumb on the scale: without this a
#: strong player who keeps drawing weak lobbies is quoted a soft bar forever.
COHORT_DECAY_MATCHES = 3.0

#: Floor on the spread, as a fraction of the centre. Three matches can look
#: perfectly consistent by luck, and a bar placed off a near-zero spread is
#: unreachable.
MIN_SPREAD_FRACTION = 0.18

#: Ceiling on the spread, likewise. One smurf in the lobby produces a huge
#: standard deviation, and a bar placed off that lands somewhere nobody in the
#: match reached.
MAX_SPREAD_FRACTION = 0.45

#: Below this many matches there is nothing to trim: dropping the extremes of
#: three games throws away a third of the evidence.
TRIM_MIN_MATCHES = 5

#: How far a baseline may fall per submitted match, as a fraction.
#:
#: The bar has to move down when someone genuinely gets worse, and must not
#: move down fast enough to be worth engineering. Tanking is the obvious attack
#: on a wager quoted from your own history: lose four games on purpose, get a
#: bar you can clear in your sleep, then play properly. A ratchet makes that
#: cost more matches than the payout is worth, while an honest decline still
#: reaches its true level within a handful of games.
#:
#: Rising is deliberately not limited. Improving is not an exploit, and a bar
#: that lags real improvement is one the player beats every time.
MAX_FALL_PER_MATCH = 0.08

#: A result this many spreads above an established baseline is not a good day.
#: It is not proof of anything either, which is why it raises a flag for review
#: rather than blocking a payout.
ANOMALY_SIGMA = 3.0


@dataclass(frozen=True)
class Baseline:
    """The centre and spread a bar is placed from, and where they came from."""

    mu: float
    sigma: float
    own_matches: int
    cohort_players: int
    source: str
    #: Anything about this record that a human should look at. Never blocks a
    #: payout on its own: an unusual run is evidence, not a verdict.
    anomalies: tuple[str, ...] = ()


def detect_anomalies(own: list[float], mu: float, sigma: float) -> tuple[str, ...]:
    """Patterns in a player's own results worth a second look.

    Two shapes matter on a wager product, and they are mirror images.

    A sudden jump far above an established level is what an account looks like
    when someone else starts playing on it, or when help arrives. A sustained
    drop below it is what tanking looks like: a bar quoted from your own history
    is only as honest as the history.

    Neither is proof. A player can have the game of their life, and a player can
    genuinely go on a bad run, so this raises a flag rather than blocking money.
    """
    if len(own) < TRIM_MIN_MATCHES or sigma <= 0:
        return ()

    flags: list[str] = []
    recent, earlier = own[-3:], own[:-3]
    if not earlier:
        return ()

    baseline = statistics.fmean(earlier)
    latest = statistics.fmean(recent)
    delta = (latest - baseline) / sigma

    if delta >= ANOMALY_SIGMA:
        flags.append("improbable_improvement")
    elif delta <= -ANOMALY_SIGMA:
        flags.append("sustained_underperformance")

    if max(own) > 0 and max(own) >= baseline + ANOMALY_SIGMA * 2 * sigma:
        flags.append("single_outlier_result")
    return tuple(flags)


def _trimmed(values: list[float]) -> list[float]:
    """Drop the single best and worst result, once there are enough to spare.

    One extraordinary game, in either direction, should not decide what someone
    is asked to clear for the next month. Everybody has a 40-kill game and
    everybody has a game where they disconnect at round three.
    """
    if len(values) < TRIM_MIN_MATCHES:
        return values
    ordered = sorted(values)
    return ordered[1:-1]


def _sample(values: list[float], robust: bool = False) -> tuple[float, float] | None:
    """Centre and spread. `robust` uses the median, for the lobby.

    A 5v5 lobby routinely contains one player on a completely different level.
    Their line is real, but it is not evidence about the bracket, and a mean
    lets one of them move everyone else's bar.
    """
    if not values:
        return None
    centre = statistics.median(values) if robust else statistics.fmean(values)
    sigma = statistics.pstdev(values) if len(values) > 1 else 0.0
    return centre, sigma


def compute(
    metric: str,
    own: list[float],
    cohort: list[float],
    lifetime_kd: float | None = None,
) -> Baseline:
    """Blend the three sources into one centre and spread. Pure, so testable."""
    pop_mu, pop_sigma = POPULATION[metric]

    own_stat = _sample(_trimmed(own))
    cohort_stat = _sample(cohort, robust=True)

    # A brand new account has no matches here and usually no public stats
    # either, so the population number is the whole answer for its first wager.
    # That is the right default: it is what an average matchmaking player posts,
    # so the first bar is neither free nor impossible, and one submitted match
    # replaces most of it.
    #
    # Where lifetime stats are public they pull that starting point toward the
    # player. Deliberately only halfway: the figure is cumulative across casual,
    # deathmatch and bot games, so it says something about a player but not
    # enough to be taken at face value.
    if lifetime_kd is not None and metric == "cs2_kd_ratio" and not own_stat:
        pop_mu = (pop_mu + lifetime_kd) / 2

    weights: list[tuple[float, float]] = [(pop_mu, 1.0)]
    if cohort_stat is not None:
        decay = COHORT_DECAY_MATCHES / (COHORT_DECAY_MATCHES + len(own))
        weights.append((cohort_stat[0], COHORT_WEIGHT * decay))
    if own_stat is not None:
        weights.append((own_stat[0], len(own) * OWN_WEIGHT_PER_MATCH))

    total = sum(w for _, w in weights)
    mu = sum(value * w for value, w in weights) / total

    # Spread: your own if there is enough of it, otherwise the lobby's,
    # otherwise the population's. Always floored.
    if own_stat is not None and len(own) >= 3 and own_stat[1] > 0:
        sigma = own_stat[1]
        source = "own"
    elif cohort_stat is not None and cohort_stat[1] > 0:
        sigma = cohort_stat[1]
        source = "cohort"
    else:
        sigma = pop_sigma
        source = "population"
    sigma = min(
        max(sigma, abs(mu) * MIN_SPREAD_FRACTION), abs(mu) * MAX_SPREAD_FRACTION
    )

    if own_stat is None and cohort_stat is None:
        source = "population"
    elif own and len(own) >= 5:
        source = "own"
    elif cohort:
        source = f"blend({source})"

    return Baseline(
        mu=round(mu, 4),
        sigma=round(sigma, 4),
        own_matches=len(own),
        cohort_players=len(cohort),
        source=source,
        anomalies=detect_anomalies(own, mu, sigma),
    )


async def _samples(
    session: AsyncSession, steam_id: str, metric: str
) -> tuple[list[float], list[float]]:
    """Your values, and everyone else's from the same matches."""
    rows = list(await session.scalars(select(Cs2Match).order_by(Cs2Match.match_time)))
    own: list[float] = []
    cohort: list[float] = []
    for row in rows:
        ids = row.steam_ids()
        if steam_id not in ids:
            continue
        for player in row.players or []:
            value = cs2_matches.metrics_from_line(player).get(metric)
            if value is None:
                continue
            if str(player.get("steamid")) == str(steam_id):
                own.append(value)
            else:
                cohort.append(value)
    return own, cohort


async def refresh(
    session: AsyncSession, user_id: uuid.UUID, steam_id: str
) -> dict[str, Baseline]:
    """Recompute this player's CS2 baselines from everything known so far.

    Called after a match is stored, so a bar tracks how someone is actually
    playing rather than the guess made when they signed in.
    """
    lifetime = await steam.get_cs2_lifetime_stats(steam_id)
    lifetime_kd = lifetime.kd_ratio if lifetime else None

    existing = {
        m.metric: m
        for m in await session.scalars(
            select(MetricModel).where(
                MetricModel.user_id == user_id,
                MetricModel.game == GAME_CS2_STEAM,
            )
        )
    }

    out: dict[str, Baseline] = {}
    for metric in CS2_STEAM_METRICS:
        own, cohort = await _samples(session, steam_id, metric)
        baseline = compute(metric, own, cohort, lifetime_kd)
        model = existing.get(metric)

        if model is not None:
            floored = apply_ratchet(baseline.mu, float(model.mu), int(model.n))
            if floored != baseline.mu:
                log.info(
                    "cs2.baseline_ratcheted",
                    user_id=str(user_id),
                    metric=metric,
                    computed=baseline.mu,
                    held_at=round(floored, 4),
                )
                baseline = replace(baseline, mu=round(floored, 4))

        if baseline.anomalies:
            # Logged rather than acted on. These are shapes worth reviewing, not
            # verdicts, and an automatic block on a player having a great night
            # is worse than a missed catch.
            log.warning(
                "cs2.baseline_anomaly",
                user_id=str(user_id),
                steam_id=steam_id,
                metric=metric,
                anomalies=list(baseline.anomalies),
                matches=baseline.own_matches,
            )
        out[metric] = baseline
        # `n` is what the engines read as "how much do we know". It is the count
        # of the player's own matches, never the cohort, or a bar would look
        # well-evidenced on the strength of other people's games.
        n = max(1, baseline.own_matches)
        if model is None:
            session.add(
                MetricModel(
                    user_id=user_id,
                    game=GAME_CS2_STEAM,
                    metric=metric,
                    mu=baseline.mu,
                    sigma=baseline.sigma,
                    n=n,
                )
            )
        else:
            model.mu = baseline.mu
            model.sigma = baseline.sigma
            model.n = n
    await session.flush()

    log.info(
        "cs2.baseline_refreshed",
        user_id=str(user_id),
        steam_id=steam_id,
        lifetime_kd=round(lifetime_kd, 3) if lifetime_kd else None,
        baselines={
            k: {"mu": v.mu, "sigma": v.sigma, "n": v.own_matches, "src": v.source}
            for k, v in out.items()
        },
    )
    return out


def apply_ratchet(new_mu: float, previous_mu: float, previous_n: int) -> float:
    """Limit how fast an established baseline may fall.

    A bar quoted from your own history invites exactly one attack: play badly on
    purpose, collect a bar you can clear without trying, then play normally. The
    ratchet does not prevent that, it prices it. Each tanked match buys at most
    an 8% easier bar, so moving a bar far enough to matter costs more matches
    than any single payout is worth, and the sustained drop is flagged while it
    happens.

    It deliberately does not apply until a baseline exists. A genuinely weak new
    player must be allowed to converge to their real level immediately, because
    the original complaint about this feature was a player who had just gone
    8-19 being asked for 1.25 K/D. Making that player grind ten matches to earn
    an honest bar would reintroduce the bug in slow motion.

    Rising is never limited. Improvement is not an exploit.
    """
    if previous_n < TRIM_MIN_MATCHES or previous_mu <= 0:
        return new_mu
    return max(new_mu, previous_mu * (1 - MAX_FALL_PER_MATCH))


__all__ = [
    "Baseline",
    "POPULATION",
    "apply_ratchet",
    "compute",
    "detect_anomalies",
    "refresh",
]
