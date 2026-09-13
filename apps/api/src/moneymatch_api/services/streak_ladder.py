"""The win-streak matchmaking ladder (IMPLEMENTATION_PHASES.md Phase 4).

Pure, game-agnostic, no I/O — the "climb" mechanic that shifts *who you play*
(never what you wager) as you win, and resets when you lose:

- **Win → next match targets a slightly higher opponent.** Win again → higher
  still. A transient `streak` counts consecutive wins and lifts your matchmaking
  target up a rung per win, capped.
- **Lose → streak resets to 0 → back to a similar-skill opponent.**
- **Draw / void → streak unchanged** (no climb, no punishment).

Two things fall out of this by construction:

- **Anti-smurf.** A smurf wins fast, so the ladder rockets their *target* up and
  out of the beginner pool within a few matches instead of letting them farm.
- **Fish protection.** The climb offset is always ≥ 0 and resets to 0 on a loss,
  so you are **never matched above your own level unless you climbed there by
  winning**, and a loss drops you back to your own level — never below it.

The offset is expressed in **index units** (a `rung_size` the caller supplies,
typically a fraction of a bucket width) so "slightly higher" is scale-free across
games. Direction is handled with `lower_is_better` (chess moves: a "higher"
opponent is a *lower* move count), mirroring `bucketing.index`.

Everything here is a deterministic function of numbers, so it unit-tests with no
database; the matchmaking service supplies the numbers.
"""

from __future__ import annotations

# The climb is capped so a long streak can't fling you arbitrarily far up. With a
# rung of ~half a bucket width, 6 rungs ≈ three buckets of headroom — plenty for a
# smurf to be pulled out of the fish pool, without ever being unbounded.
STREAK_MAX_RUNGS = 6

# Fraction of a bucket's width that one consecutive win lifts the target by. Half
# a bucket means it takes two wins to fully cross into the next band — a gentle,
# legible "slightly higher each time" climb rather than a jump.
DEFAULT_RUNG_FRACTION_OF_BUCKET = 0.5


def streak_after(current_streak: int, won: bool | None) -> int:
    """The streak after a settled 1v1.

    - `won is True`  → +1 (climb).
    - `won is False` → 0 (reset to your own level).
    - `won is None`  → unchanged (a draw or a voided/unverifiable game neither
      climbs nor punishes — it simply didn't happen for ladder purposes).
    """
    current = max(0, current_streak)
    if won is True:
        return current + 1
    if won is False:
        return 0
    return current


def climb_rungs(streak: int, *, max_rungs: int = STREAK_MAX_RUNGS) -> int:
    """How many rungs a streak has earned — `min(streak, max_rungs)`, never below
    0. `climb_rungs(0) == 0` is the fish-protection floor: at no streak you match
    at your own level."""
    return max(0, min(streak, max_rungs))


def target_offset(
    streak: int, *, rung_size: float, max_rungs: int = STREAK_MAX_RUNGS
) -> float:
    """The (non-negative) amount, in index units, to lift the matchmaking target
    above your own index. Always ≥ 0 — the ladder only ever aims you *up*."""
    return climb_rungs(streak, max_rungs=max_rungs) * abs(rung_size)


def matchmaking_target(
    own_index: float,
    streak: int,
    *,
    rung_size: float,
    lower_is_better: bool = False,
    max_rungs: int = STREAK_MAX_RUNGS,
) -> float:
    """The index a win-streaked player should be matched *around*.

    Higher-is-better: `own_index + offset`. Lower-is-better (chess moves, where a
    stronger opponent posts a *lower* value): `own_index − offset`. At streak 0 the
    target is exactly your own index (fish protection).
    """
    offset = target_offset(streak, rung_size=rung_size, max_rungs=max_rungs)
    return own_index - offset if lower_is_better else own_index + offset


def target_bucket(
    own_bucket: int,
    streak: int,
    *,
    num_buckets: int,
    rungs_per_bucket: float = 1.0 / DEFAULT_RUNG_FRACTION_OF_BUCKET,
    max_rungs: int = STREAK_MAX_RUNGS,
) -> int:
    """A convenience target *bucket* for bucket-queue matchmaking: your own bucket
    plus the rungs climbed (translated to whole buckets), clamped to the top band
    and **never below your own bucket**.

    `rungs_per_bucket` is how many win-rungs equal one whole bucket (default 2, the
    inverse of a half-bucket rung), so two wins move you up one matchmaking band.
    """
    if num_buckets <= 0:
        return max(0, own_bucket)
    rungs = climb_rungs(streak, max_rungs=max_rungs)
    bucket_climb = int(rungs // max(1e-9, rungs_per_bucket))
    return min(own_bucket + bucket_climb, num_buckets - 1)


def rung_size_from_bucket_width(
    bucket_width: float, *, fraction: float = DEFAULT_RUNG_FRACTION_OF_BUCKET
) -> float:
    """A sensible per-market rung: a fraction of a bucket's index width. Falls back
    to a small positive step when a width isn't known yet (single-bucket market)."""
    if bucket_width <= 0:
        return 1.0
    return bucket_width * fraction
