"""Phase 4 — placement systems & the confidence-gated stake ladder.

Pure logic (no DB). Two things live here:

1. **The stake ladder** — the smurf defense. A new player's first placement is a
   guess; a strong player on a fresh account (a *smurf*) is underrated at first.
   We bound the damage by capping the stake as a function of **index confidence**,
   not raw game count — so the cap only opens once the number has stopped moving,
   which is exactly when a smurf has been caught up to. A still-climbing index
   (smurf or genuine learner) stays at the floor stake; a settled index unlocks
   the ladder.

2. **The placement decision** — given a game's placement *system* and what we
   know about a freshly linked account, decide the starting bucket source and
   whether stakes are provisional. The System-1 (history) vs System-2 (no
   history) split is data in `markets.BucketMarket.placement`; this module turns
   it into a `Placement`.

The ladder rungs reuse the existing server-defined entry presets
(`constants.ENTRY_PRESETS_CENTS` = $5 / $10 / $25) so the bucketing layer never
invents its own stake amounts, then adds an uncapped top rung.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...constants import (
    ENTRY_PRESETS_CENTS,
    METRIC_PROVISIONAL_MIN_N,
)
from .markets import SYSTEM_HISTORY, SYSTEM_NO_HISTORY, BucketMarket

# Confidence thresholds that unlock each rung. Deliberately conservative: the cap
# only rises once the index is genuinely settled, so a fast-improving (possibly
# smurf) account is held at the floor while it would be most dangerous.
#   conf <  0.60 → rung 0  ($5 cap)
#   conf <  0.80 → rung 1  ($10 cap)
#   conf <  0.92 → rung 2  ($25 cap)
#   conf >= 0.92 → rung 3  (uncapped)
LADDER_CONFIDENCE_GATES: tuple[float, ...] = (0.60, 0.80, 0.92)

# Cap per rung, in cents. First three mirror ENTRY_PRESETS_CENTS; last is uncapped.
UNCAPPED = None  # sentinel: no stake cap
LADDER_CAPS_CENTS: tuple[int | None, ...] = (*ENTRY_PRESETS_CENTS, UNCAPPED)


def stake_rung(index_confidence: float) -> int:
    """Which ladder rung (0..3) an index confidence unlocks."""
    rung = 0
    for gate in LADDER_CONFIDENCE_GATES:
        if index_confidence >= gate:
            rung += 1
        else:
            break
    return rung


def stake_cap_cents(index_confidence: float, *, provisional: bool) -> int | None:
    """The maximum stake (cents) allowed right now, or `None` for uncapped.

    A **provisional** market (too few graded samples) is always held at the
    ladder floor regardless of confidence — the number could still be a fluke of
    a handful of games. Once non-provisional, the cap is driven purely by how
    settled the index is.
    """
    if provisional:
        return LADDER_CAPS_CENTS[0]
    return LADDER_CAPS_CENTS[stake_rung(index_confidence)]


def is_provisional(n_samples: int) -> bool:
    """Below the shared provisional floor, a market can't back a full-stake wager
    (reuses the existing `METRIC_PROVISIONAL_MIN_N`)."""
    return n_samples < METRIC_PROVISIONAL_MIN_N


def within_cap(stake_cents: int, cap_cents: int | None) -> bool:
    """Whether a requested stake is allowed under the current cap."""
    return cap_cents is None or stake_cents <= cap_cents


@dataclass(frozen=True)
class Placement:
    """The outcome of onboarding a freshly linked account for one market."""

    market_key: str
    #: 'history' | 'prior' | 'live' — where the starting bucket came from.
    placed_from: str
    provisional: bool
    stake_cap_cents: int | None
    #: The starting bucket, or None when it can't be known yet (System 2 with no
    #: prior → the caller seeds the lowest bucket).
    starting_bucket: int | None


def place_account(
    market: BucketMarket,
    *,
    n_samples: int,
    index_confidence: float,
    starting_bucket: int | None,
    has_prior: bool = False,
) -> Placement:
    """Decide a market's placement for a newly linked account.

    - **System 1 (history).** If the backfill cleared the market's history floor,
      the account is placed non-provisionally from history with its cap driven by
      confidence. Below the floor it is provisional (floor stake) until it fills.
    - **System 2 (no history).** There is nothing to backfill, so the account is
      provisional from match one. If a weak prior exists (e.g. Steam lifetime
      stats) it seeds a starting bucket (`placed_from='prior'`); otherwise the
      caller seeds the lowest bucket and it is `placed_from='live'`. Either way
      the stake is capped by the ladder until the live index settles.
    """
    if market.placement == SYSTEM_HISTORY:
        provisional = n_samples < market.history_floor or is_provisional(n_samples)
        placed_from = "history"
        cap = stake_cap_cents(index_confidence, provisional=provisional)
        return Placement(
            market_key=market.key_str,
            placed_from=placed_from,
            provisional=provisional,
            stake_cap_cents=cap,
            starting_bucket=starting_bucket,
        )

    if market.placement == SYSTEM_NO_HISTORY:
        provisional = is_provisional(n_samples)
        placed_from = "prior" if has_prior else "live"
        cap = stake_cap_cents(index_confidence, provisional=provisional)
        return Placement(
            market_key=market.key_str,
            placed_from=placed_from,
            provisional=provisional,
            stake_cap_cents=cap,
            starting_bucket=starting_bucket,
        )

    raise ValueError(f"unknown placement system: {market.placement!r}")
