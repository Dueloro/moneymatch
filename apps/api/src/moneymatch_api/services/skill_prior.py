"""What a typical game looks like, before we know much about *you*.

A pool quotes your bar from your own history. That is right in principle and
badly wrong in practice for the first dozen games, because a mean and a spread
taken from a handful of matches are mostly noise. A player with 9 chess games
had a measured spread of 18.1 moves around a mean of 25.7, and the hard bar came
out at **minus six moves**: not merely hard, but impossible, and no chess game
has ever ended in a negative number of moves.

Two fixes live here, and the third is in `fairness.py`.

1. **A prior from rating.** How long a chess game runs depends on how good the
   players are, and Elo is known the moment an account is linked. So there is a
   sensible expectation for a 1058-rated player before they play a single game
   on our platform.
2. **Shrinkage.** Blend the player's own numbers toward that expectation,
   weighted by how many games they actually have. Nine games barely move it;
   fifty games own it.

(3. `fairness.py` places the bar on a lognormal rather than a normal, which is
what stops it going negative.)

## The measurement

Sampled 2026-08-09 from eight finished Lichess arena tournaments, standard
chess only (bullet/blitz/rapid/classical), **4,647 games**, taking each game's
full-move count against the mean of the two players' ratings.

Draws are excluded, leaving **4,526 decisive games** (draws were 2.6%). The
metric this backs is `chess_moves`, which only counts matches you *won*
(`METRIC_REQUIRES_WIN`), so the quantity to model is the length of a game
somebody won. Every decisive game is a win for exactly one of its players, so
the population of decisive games is precisely that distribution. Leaving draws
in shifted the centre about half a move long, since drawn games run longer.

    rating band      n    mean moves    sd
    1000           158       25.5      11.7
    1200           273       29.4      11.8
    1400           673       32.0      12.0
    1600          1107       32.3      11.5
    1800          1318       34.4      11.7
    2000           698       37.7      12.5
    2200           248       39.1      13.4
    -----------------------------------------
    decisive      4526

Two things fall out of that table:

- **Mean length rises with rating**, near enough linearly. Stronger players
  blunder less, so fewer games end early. A weighted least-squares fit over the
  bands gives roughly one extra move per 100 rating points.
- **The spread barely moves.** The standard deviation sits near 12 moves in
  every band. So a single population spread is a defensible prior, while the
  centre has to follow rating.

Re-run `scripts/research/lichess_game_length.py` to refresh these numbers. It
samples whichever arenas have finished recently, so the intercept and the slope
trade against each other between runs; judge a run by its *predictions*, which
have held within about a move (a second sample gave 27.8 and 37.0 moves at 1000
and 2000, against 26.8 and 36.9 here).
"""

from __future__ import annotations

from ..models.linked_account import LinkedAccount

# --------------------------------------------------------------------------- #
# Fitted from the sample above (weighted by games per band).
# --------------------------------------------------------------------------- #

#   mean_moves(elo) = _MOVES_INTERCEPT + _MOVES_PER_ELO * elo
# which reads as ~27 moves at 1000 and ~37 at 2000.
_MOVES_INTERCEPT = 16.65
_MOVES_PER_ELO = 0.01013

# Flat across every band we measured (11.5 to 13.4, weighted mean 11.94).
_MOVES_SIGMA = 11.94

# Outside the range we sampled the linear fit stops being evidence, so the
# centre is held at the edges rather than extrapolated to absurdity.
_RATING_FLOOR, _RATING_CEIL = 800.0, 2600.0

# Used when an account is linked but its rating cannot be read. Deliberately
# mid-table: for a fewest-moves metric a too-high centre yields a *roomier*
# bar, so an unknown rating errs toward achievable rather than impossible.
_ASSUMED_RATING = 1500.0

# How many games of prior the blend is worth. At n = 10 your own record and the
# prior weigh the same; by n = 40 you are 80% yourself. Chosen so that a player
# is quoted a sane bar immediately and a settled one within a normal session's
# worth of games.
PRIOR_WEIGHT = 10.0

# Only metrics with a measured prior appear here. Everything else keeps its raw
# sample, so adding a game can never silently inherit chess's numbers.
_PRIORS: dict[str, tuple[float, float]] = {}


def _chess_moves_prior(rating: float | None) -> tuple[float, float]:
    elo = _ASSUMED_RATING if rating is None else rating
    elo = min(_RATING_CEIL, max(_RATING_FLOOR, elo))
    return _MOVES_INTERCEPT + _MOVES_PER_ELO * elo, _MOVES_SIGMA


def prior_for(metric: str, rating: float | None) -> tuple[float, float] | None:
    """Expected (mean, spread) for `metric` at `rating`, or None if unmeasured.

    Returning None is the honest answer for a metric nobody has sampled, and
    callers fall back to the player's raw record.
    """
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
    """Blend a player's own record toward the prior, by how much record there is.

    The mean is a weighted average; the spread is blended in *variance* rather
    than in standard deviation, which is the form that composes correctly (a
    variance is an average of squared deviations, so averaging variances keeps
    the units honest).

    With no prior the player's own numbers are returned untouched, which is the
    only honest option for a metric nobody has measured.

    Of the two, the spread matters more. A mean off a small sample is wrong by
    roughly σ/√n and lands the bar slightly high or low; a *spread* off the same
    sample is wrong by roughly σ/√(2n) and decides how far the bar travels from
    the centre, multiplied by k. That is the term that produced a negative bar.
    """
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
    """The linked account's rating on its primary speed, from the snapshot.

    Captured per speed at link time, so reading it costs no extra host call.
    Used both to seed the prior here and to seat aggregate tournament fields,
    which have no per-match model to take a mean and spread from.
    """
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
