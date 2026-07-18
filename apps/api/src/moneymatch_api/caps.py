"""Phase-1 launch caps — the single config table (10-phase-7 §1).

Every numeric staking/money limit from `docs/product/overview.md` §7.3 lives
here, in one place, so risk/compliance tune values without hunting through
services. The schema is load-bearing; the values are tunable. Enforcement stays
server-side at the boundary (00-README §3.1): `limits_service` reads the entry
band + daily caps, the wallet router reads the withdrawal minimum, and the KYC
policy hook reads the cumulative-entry threshold.

These are integer cents. The daily-cap + concurrency defaults are re-exported to
`models/wallet.py` so the `limits` table server-defaults and this table can
never drift.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caps:
    """Phase-1 caps (overview.md §7.3). All money fields are integer cents."""

    # Per-contest entry band, enforced at escrow time in addition to the
    # server-defined presets (a preset is always inside the band; the band is
    # the boundary guarantee that survives a preset-table change).
    min_entry_cents: int = 100  # $1
    max_entry_cents: int = 10_000  # $100

    # Per-user trailing-24h caps (the `limits` table's defaults come from here).
    daily_loss_cap_cents: int = 20_000  # $200
    daily_entry_cap_cents: int = 50_000  # $500
    max_concurrent_contests: int = 3

    # Cumulative trailing-24h entries at/above which real KYC would be required
    # (kyc_required policy hook; inert at MVP because kyc_live is False).
    kyc_entry_threshold_cents: int = 50_000  # $500 cumulative entries

    # Demo withdrawals below this are refused (overview.md §7.3 withdrawal min).
    withdrawal_min_cents: int = 2_000  # $20


CAPS = Caps()
