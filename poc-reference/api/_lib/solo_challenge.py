"""Algorithmic Solo Challenge engine — POOLED solo tournament (overview §10).

Players each pay an entry fee into a shared pool for a given game + qualifying
standard. Everyone plays their own game; the platform verifies API telemetry
against a **qualifying skill standard** (a measurable, player-controlled metric —
never a win/loss or a prop bet). Entrants who clear the standard split the pool
**minus a fixed platform rake**; if nobody clears (or the pool is under-subscribed)
every entry is refunded.

There is **no house**: the prize comes entirely from entrants' pooled fees, the
platform never funds a prize and holds no outcome position. Settlement invariant
``sum(payouts) + rake == sum(entries)`` — the same neutral-operator escrow/rake
model the peer-to-peer side uses (overview §2 / §7.1). This is the legally
compliant structure for skill-based gaming; play-money in the demo.

Two load-bearing properties:

1. **Pooled, rake-only.** Rake is taken *only* when a real prize is distributed
   (at least one clearer). No clearers ⇒ full refund, zero rake — the platform
   earns nothing on a round it does not pay out, so it never profits from player
   failure.
2. **Geo-fence first.** ``assert_can_enter`` runs *before* any entry fee is
   escrowed, blocking the 14 "Any Chance" states (overview §10 guardrails).

Logic is pure (no I/O) so it is unit-testable exactly like the settlement code.
"""

from __future__ import annotations

import random
import time
import uuid
from typing import Optional

from _lib.schemas import (
    Comparator,
    MetricTarget,
    SoloEntry,
    SoloGame,
    SoloPool,
    TelemetrySample,
)

# The 14 "Any Chance" states money match geo-fences out of real-money skill
# wagering. Kept in sync with the client gate in src/components/Onboarding/
# Landing.tsx (EXCLUDED_STATES) and overview §9.2 / §10. Full state names match
# the residence dropdown values.
RESTRICTED_STATES = frozenset({
    "Arizona", "Arkansas", "Connecticut", "Delaware", "Florida", "Indiana",
    "Louisiana", "Maryland", "Minnesota", "Montana", "South Carolina",
    "South Dakota", "Tennessee", "Wyoming",
})

DEFAULT_RAKE_PCT = 0.10

_round2 = lambda x: round(x, 2)  # noqa: E731


class RegionBlockedError(Exception):
    """Raised when a player's residence state is geo-fenced (overview §10)."""


# ---------------------------------------------------------------------------
# Geo-fence middleware (must run before any entry fee is escrowed)
# ---------------------------------------------------------------------------


def is_region_restricted(state: Optional[str]) -> bool:
    """True if real-money play is blocked in this state."""
    return state is None or state.strip() in RESTRICTED_STATES


def assert_can_enter(state: Optional[str]) -> None:
    """Geo-fence guard. Raise before escrowing an entry in a blocked region."""
    if is_region_restricted(state):
        raise RegionBlockedError(
            f"Solo challenges are not available in {state or 'an unspecified region'}."
        )


# ---------------------------------------------------------------------------
# Pool creation + entry
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_pool(
    game: SoloGame,
    metric_target: MetricTarget,
    entry_fee: float,
    rake_pct: float = DEFAULT_RAKE_PCT,
    min_entrants: int = 2,
) -> SoloPool:
    """Open an empty pooled solo tournament for a game + qualifying standard."""
    return SoloPool(
        id=uuid.uuid4().hex,
        game=game,
        metric_target=metric_target,
        entry_fee=_round2(entry_fee),
        rake_pct=rake_pct,
        min_entrants=min_entrants,
        status="OPEN",
        created_at=_now_ms(),
    )


def enter_pool(pool: SoloPool, player_id: str, state: str) -> SoloPool:
    """Escrow an entry into the pool. Geo-fence runs BEFORE the fee is taken.

    Returns the pool with the new LOCKED entry and an updated ``pool`` total.
    Idempotent per player: a player_id already entered is not double-charged.
    """
    assert_can_enter(state)  # geo-fence BEFORE charging
    if any(e.player_id == player_id for e in pool.entrants):
        return pool  # already entered; no double escrow

    pool.entrants.append(SoloEntry(player_id=player_id, state=state, status="LOCKED"))
    pool.pool = _round2(pool.entry_fee * len(pool.entrants))
    return pool


# ---------------------------------------------------------------------------
# Demo lobby — seeded open pools with bot entrants (so a pool is joinable)
# ---------------------------------------------------------------------------

# Clearly-bot handles for seeded pool entrants. The demo has no second real
# player, so pools are pre-populated with bots (overview §8.1 / roadmap §1.5),
# the same simulation the peer-to-peer lobby uses.
_BOT_HANDLES = [
    "knightfork", "enpassant", "pawnstorm", "zugzwanger", "aerialace",
    "elixirgod", "boostking", "skywarden", "tiltproof", "cleansheet",
]


def _seed_bots(pool: SoloPool, n: int, rng: random.Random) -> None:
    """Pre-enter ``n`` bot entrants (bots bypass the human geo-fence)."""
    for _ in range(n):
        handle = f"{rng.choice(_BOT_HANDLES)}{rng.randint(10, 99)}"
        pool.entrants.append(SoloEntry(player_id=f"bot_{handle}", state="bot", status="LOCKED"))
    pool.pool = _round2(pool.entry_fee * len(pool.entrants))


# (game, MetricTarget, entry_fee, bot_count) — varied across the three titles.
_LOBBY_SEEDS: list[tuple[SoloGame, MetricTarget, float, int]] = [
    ("chess.lichess",
     MetricTarget(metric="chess_accuracy_pct", comparator="gte", threshold=82,
                  secondary_metric="chess_moves", secondary_comparator="gte", secondary_threshold=20),
     5.0, 3),
    ("chess.lichess",
     MetricTarget(metric="chess_accuracy_pct", comparator="gte", threshold=75,
                  secondary_metric="chess_moves", secondary_comparator="gte", secondary_threshold=20),
     1.0, 2),
    ("rocketleague.psyonix",
     MetricTarget(metric="rl_aerial_accuracy_pct", comparator="gte", threshold=60,
                  secondary_metric="rl_match_score", secondary_comparator="gte", secondary_threshold=500),
     5.0, 3),
    ("clashroyale.supercell",
     MetricTarget(metric="cr_crown_tower_damage", comparator="gte", threshold=4000,
                  secondary_metric="cr_total_elixir", secondary_comparator="lte", secondary_threshold=30),
     10.0, 3),
    ("clashroyale.supercell",
     MetricTarget(metric="cr_crown_tower_damage", comparator="gte", threshold=3000),
     5.0, 2),
    ("rocketleague.psyonix",
     MetricTarget(metric="rl_match_score", comparator="gte", threshold=700),
     10.0, 2),
    ("cs2.faceit",
     MetricTarget(metric="cs2_kd_ratio", comparator="gte", threshold=1.2,
                  secondary_metric="cs2_headshot_pct", secondary_comparator="gte", secondary_threshold=45),
     5.0, 3),
    ("cs2.faceit",
     MetricTarget(metric="cs2_kd_ratio", comparator="gte", threshold=1.0),
     10.0, 2),
    ("dota2.opendota",
     MetricTarget(metric="dota2_kda_ratio", comparator="gte", threshold=3.0,
                  secondary_metric="dota2_gpm", secondary_comparator="gte", secondary_threshold=450),
     5.0, 3),
    ("dota2.opendota",
     MetricTarget(metric="dota2_gpm", comparator="gte", threshold=550),
     10.0, 2),
]


def generate_solo_lobby(rng: random.Random | None = None) -> list[SoloPool]:
    """Build a set of OPEN pooled tournaments, each seeded with bot entrants."""
    r = rng or random
    pools: list[SoloPool] = []
    for game, target, entry, bots in _LOBBY_SEEDS:
        pool = create_pool(game, target, entry_fee=entry, rake_pct=DEFAULT_RAKE_PCT, min_entrants=2)
        _seed_bots(pool, bots, r)
        pools.append(pool)
    return pools


# ---------------------------------------------------------------------------
# Telemetry grading + pool settlement (mock verification webhook)
# ---------------------------------------------------------------------------


def _passes(value: float, comparator: Comparator, threshold: float) -> bool:
    return value >= threshold if comparator == "gte" else value <= threshold


def grade_entry(metric_target: MetricTarget, game: SoloGame, telemetry: Optional[TelemetrySample]) -> tuple[Optional[bool], str]:
    """Grade one entrant's telemetry against the qualifying standard.

    Returns ``(cleared, detail)`` where ``cleared`` is True/False, or ``None`` if
    the entry cannot be verified (missing telemetry / metric) — an un-verifiable
    entry is refunded at settlement, never counted as a failure.
    """
    if telemetry is None:
        return None, "No telemetry reported — entry refunded."
    if telemetry.game != game:
        return None, "Telemetry game mismatch — entry refunded."

    metrics = telemetry.metrics
    target = metric_target
    if target.metric not in metrics:
        return None, f"Metric '{target.metric}' not reported — entry refunded."

    primary_value = metrics[target.metric]
    primary_ok = _passes(primary_value, target.comparator, target.threshold)
    note = f"{target.metric}={primary_value:g} {target.comparator} {target.threshold:g} [{'ok' if primary_ok else 'miss'}]"

    secondary_ok = True
    if target.secondary_metric is not None:
        if target.secondary_metric not in metrics:
            return None, f"Secondary metric '{target.secondary_metric}' not reported — entry refunded."
        sec_value = metrics[target.secondary_metric]
        secondary_ok = _passes(sec_value, target.secondary_comparator or "gte", target.secondary_threshold or 0.0)
        note += (
            f"; {target.secondary_metric}={sec_value:g} "
            f"{target.secondary_comparator} {target.secondary_threshold:g} [{'ok' if secondary_ok else 'miss'}]"
        )

    cleared = primary_ok and secondary_ok
    return cleared, ("Standard cleared: " if cleared else "Standard not met: ") + note + "."


def settle_pool(pool: SoloPool, telemetry: dict[str, TelemetrySample]) -> SoloPool:
    """Grade every entry and distribute the pool to clearers, minus rake.

    Funding rules (no house, neutral operator):
      * Under ``min_entrants`` → CANCELED, every entry refunded, zero rake.
      * No clearers → SETTLED, every entry refunded, zero rake (platform earns
        nothing on a round it does not pay out).
      * ≥1 clearer → rake = pool * rake_pct; clearers split (pool − rake) equally;
        non-clearers get 0 (their entry funds the clearers' prize).

    Invariant in all cases: ``sum(payouts) + rake == sum(entries)``.
    """
    now = _now_ms()
    pool.pool = _round2(pool.entry_fee * len(pool.entrants))

    # Grade everyone first.
    graded: list[tuple[SoloEntry, Optional[bool], str]] = []
    for e in pool.entrants:
        cleared, detail = grade_entry(pool.metric_target, pool.game, telemetry.get(e.player_id))
        e.cleared = cleared
        e.detail = detail
        graded.append((e, cleared, detail))

    def refund_all(status: str) -> SoloPool:
        for e in pool.entrants:
            e.status = "REFUNDED"
            e.payout = pool.entry_fee
        pool.rake = 0.0
        pool.prize_pool = 0.0
        pool.status = status  # "CANCELED" or "SETTLED" (no clearers)
        pool.resolved_at = now
        return pool

    if len(pool.entrants) < pool.min_entrants:
        return refund_all("CANCELED")

    clearers = [e for e, cleared, _ in graded if cleared is True]
    if not clearers:
        # No verifiable winner — refund every entry, take no rake.
        return refund_all("SETTLED")

    # Un-verifiable entries are refunded out of the pool first; only the
    # remaining (distributable) money is raked and split among clearers, so the
    # rake is always >= 0 and comes off the prize, never the refunds.
    unverifiable = [e for e, cleared, _ in graded if cleared is None]
    refunds_total = _round2(pool.entry_fee * len(unverifiable))
    distributable = _round2(pool.pool - refunds_total)

    rake = _round2(distributable * pool.rake_pct)
    share = _round2((distributable - rake) / len(clearers))

    distributed = 0.0
    for e, cleared, _ in graded:
        if cleared is True:
            e.status = "CLEARED"
            e.payout = share
            distributed = _round2(distributed + share)
        elif cleared is False:
            e.status = "MISSED"
            e.payout = 0.0          # entry funds the clearers' prize
        else:  # un-verifiable — refund the entry
            e.status = "REFUNDED"
            e.payout = pool.entry_fee

    # Absorb any rounding remainder into the rake so the invariant holds exactly:
    # sum(payouts) + rake == pool.
    pool.rake = _round2(pool.pool - distributed - refunds_total)
    pool.prize_pool = distributed
    pool.status = "SETTLED"
    pool.resolved_at = now
    return pool
