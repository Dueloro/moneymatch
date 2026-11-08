"""The `KycProvider` seam."""

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
    client_action: str | None = None


@runtime_checkable
class KycProvider(Protocol):
    """The contract every identity-verification vendor implements."""

    name: str

    async def start_verification(self, user_id: uuid.UUID) -> KycVerification: ...

    async def get_status(self, user_id: uuid.UUID) -> KycStatus: ...
