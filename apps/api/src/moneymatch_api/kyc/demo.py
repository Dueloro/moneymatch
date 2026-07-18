"""`DemoKycProvider` — the only `KycProvider` at MVP.

There is no real verification vendor; the demo provider auto-verifies so the
seam is demonstrably exercisable. It is never reached on the hot path at MVP
because `kyc_required` returns False everywhere — it exists so the protocol has
a concrete implementation and the resolver has something to return.
"""

from __future__ import annotations

import uuid

from .base import KycStatus, KycVerification

PROVIDER_NAME = "demo"


class DemoKycProvider:
    """Auto-verifying stub behind the `KycProvider` protocol."""

    name = PROVIDER_NAME

    async def start_verification(self, user_id: uuid.UUID) -> KycVerification:
        return KycVerification(
            provider=self.name,
            reference=str(user_id),
            status=KycStatus.VERIFIED,
            client_action=None,
        )

    async def get_status(self, user_id: uuid.UUID) -> KycStatus:
        return KycStatus.VERIFIED
