"""Pure integer-cent money math — no floats, no DB.

The PoC's `_round2` float math is a known flaw (migration-map §4.3); every split
here is exact integer arithmetic. The load-bearing rule (00-README §3.3): on
every distribution `sum(payouts) + rake == pot`, and any remainder cents from
integer division land in the **rake**, never minted or lost.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default platform rake, in basis points. 1000 bps = 10% → H2H multiplier
# 2·(1 − 0.10) = ×1.80 (02-design-system §4). Rake is config, never an odds line.
DEFAULT_RAKE_BPS = 1000

BPS_DENOMINATOR = 10_000


@dataclass(frozen=True)
class Split:
    """Result of distributing a pot: one payout per winner plus the rake.

    Invariant (asserted in `__post_init__`): ``sum(payouts) + rake == pot``.
    """

    pot_cents: int
    rake_cents: int
    payouts_cents: tuple[int, ...]

    def __post_init__(self) -> None:
        if sum(self.payouts_cents) + self.rake_cents != self.pot_cents:
            raise ValueError("split does not reconcile to the pot")
        if self.rake_cents < 0 or any(p < 0 for p in self.payouts_cents):
            raise ValueError("split produced a negative amount")


def rake_for(pot_cents: int, rake_bps: int = DEFAULT_RAKE_BPS) -> int:
    """Floor rake on a pot, in cents. Floor keeps rake ≤ the true percentage;
    the leftover from flooring is returned to players via `split_pot`."""
    if pot_cents < 0:
        raise ValueError("pot must be non-negative")
    if not 0 <= rake_bps <= BPS_DENOMINATOR:
        raise ValueError("rake_bps out of range")
    return pot_cents * rake_bps // BPS_DENOMINATOR


def split_pot(
    pot_cents: int, num_winners: int, rake_bps: int = DEFAULT_RAKE_BPS
) -> Split:
    """Split `pot_cents` equally among `num_winners`, taking `rake_bps` rake.

    Remainder cents from the equal division are added to the rake so the books
    reconcile exactly (00-README §3.3). With `num_winners == 0` the whole pot is
    rake (caller decides whether that means refund — a no-winner contest refunds
    and takes zero rake; that path never calls this).
    """
    if pot_cents < 0:
        raise ValueError("pot must be non-negative")
    if num_winners < 0:
        raise ValueError("num_winners must be non-negative")

    rake = rake_for(pot_cents, rake_bps)
    distributable = pot_cents - rake
    if num_winners == 0:
        return Split(pot_cents=pot_cents, rake_cents=pot_cents, payouts_cents=())

    each = distributable // num_winners
    remainder = distributable - each * num_winners
    # Remainder cents go to the rake — never split unevenly, never dropped.
    return Split(
        pot_cents=pot_cents,
        rake_cents=rake + remainder,
        payouts_cents=tuple([each] * num_winners),
    )


def h2h_multiplier_bps(rake_bps: int = DEFAULT_RAKE_BPS) -> int:
    """Derived H2H display multiplier in basis points: 2·(1 − rake). This is the
    `×1.80` on market cards — computed, never configured (02-design-system §4)."""
    return 2 * (BPS_DENOMINATOR - rake_bps)
