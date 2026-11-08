"""Pure integer-cent money math — no floats, no DB."""

from __future__ import annotations

from dataclasses import dataclass

# Default platform rake, in basis points. 1000 bps = 10% → H2H multiplier 2· = ×1.80.
DEFAULT_RAKE_BPS = 1000

BPS_DENOMINATOR = 10_000


@dataclass(frozen=True)
class Split:
    """Result of distributing a pot: one payout per winner plus the rake."""

    pot_cents: int
    rake_cents: int
    payouts_cents: tuple[int, ...]

    def __post_init__(self) -> None:
        if sum(self.payouts_cents) + self.rake_cents != self.pot_cents:
            raise ValueError("split does not reconcile to the pot")
        if self.rake_cents < 0 or any(p < 0 for p in self.payouts_cents):
            raise ValueError("split produced a negative amount")


def rake_for(pot_cents: int, rake_bps: int = DEFAULT_RAKE_BPS) -> int:
    """Floor rake on a pot, in cents."""
    if pot_cents < 0:
        raise ValueError("pot must be non-negative")
    if not 0 <= rake_bps <= BPS_DENOMINATOR:
        raise ValueError("rake_bps out of range")
    return pot_cents * rake_bps // BPS_DENOMINATOR


def split_pot(
    pot_cents: int, num_winners: int, rake_bps: int = DEFAULT_RAKE_BPS
) -> Split:
    """Split `pot_cents` equally among `num_winners`, taking `rake_bps` rake."""
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
    """Derived H2H display multiplier in basis points: 2·(1 − rake)."""
    return 2 * (BPS_DENOMINATOR - rake_bps)


def pool_multiplier_estimate_bps(
    p_target: float,
    room_size: int,
    rake_bps: int = DEFAULT_RAKE_BPS,
) -> int:
    """Estimated pool tier multiplier, in basis points, on your own entry."""
    take_home_bps = BPS_DENOMINATOR - rake_bps
    cap_bps = max(0, room_size) * take_home_bps
    if p_target <= 0:
        return cap_bps
    return min(round(take_home_bps / p_target), cap_bps)


def split_weighted(
    pot_cents: int, weights: tuple[int, ...], rake_bps: int = DEFAULT_RAKE_BPS
) -> Split:
    """Takes `rake_bps` off the pot, then floors each place's share of the
    distributable by weight; any flooring remainder lands in the **rake** so the
    books reconcile exactly.
    """
    if pot_cents < 0:
        raise ValueError("pot must be non-negative")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")

    rake = rake_for(pot_cents, rake_bps)
    distributable = pot_cents - rake
    wsum = sum(weights)
    if wsum == 0:
        # No places to pay (no ranked finishers) — whole pot is rake; the caller decides
        # whether that path means refund (it does — and never calls here).
        return Split(pot_cents=pot_cents, rake_cents=pot_cents, payouts_cents=())

    slices = tuple(distributable * w // wsum for w in weights)
    remainder = distributable - sum(slices)
    return Split(
        pot_cents=pot_cents,
        rake_cents=rake + remainder,
        payouts_cents=slices,
    )
