"""The `KycProvider` seam (10-phase-7 §1).

Identity verification is a real-rails, Stage-C concern
(`docs/legal/legal-compliance.md` §5). The MVP ships the interface and the
`users.kyc_status` column so a real provider (Persona/Onfido/etc.) is an
additive integration: implement this protocol, register it, and flip
`kyc_live`. Nothing at MVP advances a user past `none` — the `kyc_required`
policy hook returns False everywhere (see `policy.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class KycStatus(StrEnum):
    """Mirrors `users.kyc_status` (the DB check constraint is the source)."""

    NONE = "none"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True)
class KycVerification:
    """A verification session started for a user."""

    provider: str
    reference: str
    status: KycStatus
    client_action: str | None = None  # redirect / SDK token for a real provider


@runtime_checkable
class KycProvider(Protocol):
    """The contract every identity-verification vendor implements."""

    name: str

    async def start_verification(self, user_id: uuid.UUID) -> KycVerification: ...

    async def get_status(self, user_id: uuid.UUID) -> KycStatus: ...
