"""Enforcement stays server-side at the boundary: `limits_service` reads the entry
band + daily caps, the wallet router reads the withdrawal minimum, and the KYC
policy hook reads the cumulative-entry threshold.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caps:
    """Phase-1 caps. All money fields are integer cents."""

    min_entry_cents: int = 100
    max_entry_cents: int = 10_000

    daily_loss_cap_cents: int = 20_000
    daily_entry_cap_cents: int = 50_000
    daily_deposit_cap_cents: int = 100_000
    max_concurrent_contests: int = 3

    # Cumulative trailing-24h entries at/above which real KYC would be required
    # (kyc_required policy hook; inert at MVP because kyc_live is False).
    kyc_entry_threshold_cents: int = 50_000

    withdrawal_min_cents: int = 2_000


CAPS = Caps()
