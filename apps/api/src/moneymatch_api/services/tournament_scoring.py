"""Best-of-N-in-window tournament scoring (IMPLEMENTATION_PHASES.md Phase 5).

Pure, deterministic, no I/O. This is the *scoring + payout* core the phase
describes, which differs from the existing first-N tournament engine:

- A player's **score = the best scored-stat among games that *finished within* the
  window** (`ended_at ≤ window_end`). A game still in progress at the cutoff does
  **not** count — "too bad", enforced here by the timestamp filter.
- **Aggregation is a config knob** (`max` | `average` | `best_k_average`) so the
  skill-vs-chance posture can be tuned per state without a rewrite. Default `max`.
- **Ranking is deterministic** — never random: score (better first), then the
  earliest timestamp that first reached that score, then fewer games used, then a
  stable id. Ties resolve the same way on every machine.
- **Top-3 split 60/25/15 of (pot − rake)** via `money_math.split_weighted`
  (exact-to-the-gem, remainder to rake), truncated to the places actually filled.
- **Underfill → void + refund everyone.** We never top up a prize (that would make
  us a house). Peer-funded only.

The money invariant `sum(payouts) + rake == pot` is asserted before returning.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import money_math

# Aggregation modes (the config knob).
AGG_MAX = "max"
AGG_AVERAGE = "average"
AGG_BEST_K_AVERAGE = "best_k_average"

# The phase's prize split for the top 3, as integer weights.
DEFAULT_PRIZE_WEIGHTS: tuple[int, ...] = (60, 25, 15)


@dataclass(frozen=True)
class WindowGame:
    """One finished game a player produced during the tournament window."""

    value: float  # the scored stat (e.g. kills)
    ended_at_ms: int


@dataclass(frozen=True)
class PlayerScore:
    """A player's resolved tournament score (None-scored players don't place)."""

    player_id: str
    score: float
    #: When the player *first reached* `score` — the primary tie-break.
    reached_at_ms: int
    games_used: int


def _in_window(games: list[WindowGame], window_end_ms: int) -> list[WindowGame]:
    # Hard cutoff: only games that FINISHED at or before the window end count.
    return [g for g in games if g.ended_at_ms <= window_end_ms]


def score_player(
    player_id: str,
    games: list[WindowGame],
    window_end_ms: int,
    *,
    aggregation: str = AGG_MAX,
    lower_is_better: bool = False,
    best_k: int = 3,
) -> PlayerScore | None:
    """Resolve one player's score from their in-window games, or None if they had
    no game finish inside the window (they entered but don't place)."""
    eligible = _in_window(games, window_end_ms)
    if not eligible:
        return None

    # "Best" respects direction: highest value, or lowest for lower-is-better.
    def better(a: float, b: float) -> bool:
        return a < b if lower_is_better else a > b

    if aggregation == AGG_AVERAGE:
        score = sum(g.value for g in eligible) / len(eligible)
        # The reached-at for an average is the last game that completed it.
        reached_at = max(g.ended_at_ms for g in eligible)
        return PlayerScore(player_id, score, reached_at, len(eligible))

    if aggregation == AGG_BEST_K_AVERAGE:
        k = max(1, min(best_k, len(eligible)))
        ordered = sorted(eligible, key=lambda g: g.value, reverse=not lower_is_better)
        top = ordered[:k]
        score = sum(g.value for g in top) / k
        reached_at = max(g.ended_at_ms for g in top)
        return PlayerScore(player_id, score, reached_at, len(eligible))

    # AGG_MAX (default): the single best game; reached-at is the *earliest* game
    # that hit that best value (rewards getting there first on a tie).
    best_val = eligible[0].value
    for g in eligible[1:]:
        if better(g.value, best_val):
            best_val = g.value
    reached_at = min(g.ended_at_ms for g in eligible if g.value == best_val)
    return PlayerScore(player_id, best_val, reached_at, len(eligible))


def rank_players(
    scores: list[PlayerScore], *, lower_is_better: bool = False
) -> list[PlayerScore]:
    """Deterministic standings: better score first, then earliest to reach it,
    then fewer games used, then a stable player id. Never random."""

    def key(s: PlayerScore):
        # Higher-is-better wants score DESC → negate; lower-is-better wants ASC.
        primary = s.score if lower_is_better else -s.score
        return (primary, s.reached_at_ms, s.games_used, s.player_id)

    return sorted(scores, key=key)


@dataclass(frozen=True)
class TournamentSettlement:
    pot_cents: int
    rake_cents: int
    payouts: dict[str, int]  # player_id → gems (winnings or, on void, refund)
    standings: list[str]  # player ids, best first (empty on void)
    voided: bool
    reason: str

    def __post_init__(self) -> None:
        if sum(self.payouts.values()) + self.rake_cents != self.pot_cents:
            raise ValueError("tournament settlement does not reconcile to the pot")
        if self.rake_cents < 0 or any(p < 0 for p in self.payouts.values()):
            raise ValueError("tournament settlement produced a negative amount")


def settle_tournament(
    entries: dict[str, int],  # player_id → entry stake (gems)
    windows: dict[str, list[WindowGame]],
    window_end_ms: int,
    *,
    aggregation: str = AGG_MAX,
    lower_is_better: bool = False,
    rake_bps: int = money_math.DEFAULT_RAKE_BPS,
    prize_weights: tuple[int, ...] = DEFAULT_PRIZE_WEIGHTS,
    min_players: int = 2,
    best_k: int = 3,
) -> TournamentSettlement:
    """Settle a whole tournament. `entries` funds the pot; `windows` are each
    player's games. Underfill (fewer than `min_players` entered) → void + refund.
    Otherwise rank by best-in-window and split (pot − rake) 60/25/15 over the
    places actually filled.
    """
    pot = sum(entries.values())

    # Underfill → void + refund everyone their exact entry. Never top up.
    if len(entries) < min_players:
        return TournamentSettlement(
            pot_cents=pot,
            rake_cents=0,
            payouts=dict(entries),
            standings=[],
            voided=True,
            reason=f"underfill: {len(entries)} < {min_players} players",
        )

    scored = [
        s
        for pid in entries
        if (
            s := score_player(
                pid,
                windows.get(pid, []),
                window_end_ms,
                aggregation=aggregation,
                lower_is_better=lower_is_better,
                best_k=best_k,
            )
        )
        is not None
    ]

    # Nobody produced an in-window game → nothing to rank → void + refund. (A
    # contest where no result can be verified must not keep anyone's stake.)
    if not scored:
        return TournamentSettlement(
            pot_cents=pot,
            rake_cents=0,
            payouts=dict(entries),
            standings=[],
            voided=True,
            reason="no in-window results to rank",
        )

    standings = rank_players(scored, lower_is_better=lower_is_better)
    winners = standings[: len(prize_weights)]
    weights = prize_weights[: len(winners)]

    split = money_math.split_weighted(pot, weights, rake_bps=rake_bps)
    payouts = {pid: 0 for pid in entries}
    for winner, slice_cents in zip(winners, split.payouts_cents, strict=True):
        payouts[winner.player_id] = slice_cents

    return TournamentSettlement(
        pot_cents=pot,
        rake_cents=split.rake_cents,
        payouts=payouts,
        standings=[s.player_id for s in standings],
        voided=False,
        reason=f"{len(winners)} paid of {len(scored)} scored",
    )
