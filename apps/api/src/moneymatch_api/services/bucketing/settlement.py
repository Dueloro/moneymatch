"""Phase 5 — grade-vs-bar & the money invariant (pure core).

This is the settlement *arithmetic*, kept free of DB and wallet I/O so it is
exhaustively testable. The worker (Phase 5 integration) wraps this in a
transaction that holds/releases wallet money and writes the `settlement` +
`audit_events` rows; the actual pot math delegates to the existing
`services.money_math`, which already guarantees `sum(payouts) + rake == pot` to
the cent and pushes any rounding remainder into the rake (never minted or lost).

The rules, straight from `IMPLEMENTATION_BUCKETING.md` Phase 5 /
`BUCKETING_TECHNICAL_WALKTHROUGH.md` §8:

- Everyone in a room settles against the **one bar** for their bucket.
- **Cleared** = beat the bar (≥ bar for higher-is-better, ≤ bar for
  lower-is-better). Clearers split the pot; the rake is taken once.
- **Nobody clears → full refund, zero rake.** A refund is not a zero-winner
  `split_pot` (that would rake the whole pot); it returns each stake intact.
- **Fail closed.** If any member's result can't be verified, the whole contest
  is refunded — a guessed value never grades.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import money_math


def cleared_bar(value: float, bar: float, *, lower_is_better: bool) -> bool:
    """Did this result clear the bar? Symmetric in direction; the bar is
    inclusive (meeting it exactly counts as clearing)."""
    return value <= bar if lower_is_better else value >= bar


@dataclass(frozen=True)
class MemberResult:
    """One room member's settlement input."""

    player_id: str
    stake_cents: int
    #: The graded metric value, or None if it could not be verified (→ void).
    result_value: float | None


@dataclass(frozen=True)
class SettlementOutcome:
    """The full, reconcilable result of settling one room."""

    pot_cents: int
    rake_cents: int
    #: player_id → payout in cents (refund or winnings). Sums with rake to pot.
    payouts: dict[str, int]
    #: True when the contest was refunded (nobody cleared, or unverifiable data).
    refunded: bool
    reason: str

    def __post_init__(self) -> None:
        # The money invariant, enforced here as a last line of defence before any
        # caller commits it. Fail closed: a broken split must raise, not settle.
        if sum(self.payouts.values()) + self.rake_cents != self.pot_cents:
            raise ValueError("settlement does not reconcile to the pot")
        if self.rake_cents < 0 or any(p < 0 for p in self.payouts.values()):
            raise ValueError("settlement produced a negative amount")


def _refund(members: list[MemberResult], reason: str) -> SettlementOutcome:
    pot = sum(m.stake_cents for m in members)
    return SettlementOutcome(
        pot_cents=pot,
        rake_cents=0,
        payouts={m.player_id: m.stake_cents for m in members},
        refunded=True,
        reason=reason,
    )


def settle_room(
    members: list[MemberResult],
    bar: float,
    *,
    lower_is_better: bool,
    rake_bps: int = money_math.DEFAULT_RAKE_BPS,
) -> SettlementOutcome:
    """Settle one room against `bar`. Pure — returns the money split; the caller
    persists it and moves wallet funds.

    Order of the fail-closed checks matters:
    1. Any unverifiable result → refund the whole contest (never grade a guess).
    2. Nobody cleared the bar → refund everyone, zero rake.
    3. Otherwise → clearers split `pot·(1−rake)`; remainder cents go to rake.
    """
    if not members:
        return SettlementOutcome(0, 0, {}, refunded=True, reason="empty room")

    # (1) Fail closed on unverifiable data.
    if any(m.result_value is None for m in members):
        return _refund(members, "unverifiable result — voided and refunded")

    pot = sum(m.stake_cents for m in members)
    winners = [
        m
        for m in members
        if cleared_bar(m.result_value, bar, lower_is_better=lower_is_better)  # type: ignore[arg-type]
    ]

    # (2) Nobody cleared → full refund, zero rake.
    if not winners:
        return _refund(members, "nobody cleared the bar")

    # (3) Winners split the pot. money_math guarantees exact reconciliation and
    # routes rounding remainder into the rake.
    split = money_math.split_pot(pot, len(winners), rake_bps=rake_bps)
    payouts = {m.player_id: 0 for m in members}
    for m, pay in zip(winners, split.payouts_cents, strict=True):
        payouts[m.player_id] = pay
    return SettlementOutcome(
        pot_cents=pot,
        rake_cents=split.rake_cents,
        payouts=payouts,
        refunded=False,
        reason=f"{len(winners)} of {len(members)} cleared",
    )
