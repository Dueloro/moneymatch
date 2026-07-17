"""Admin surface schemas (09-phase-6).

The admin API is a plain, dense operator surface — not the consumer design
system. These models still go through Pydantic → OpenAPI → the generated TS
client so the admin web tables stay type-safe.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .wallet import LedgerEntryResponse

# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #


class FlagItem(BaseModel):
    key: str
    enabled: bool
    payload: dict[str, Any] = Field(default_factory=dict)


class FlagsResponse(BaseModel):
    flags: list[FlagItem]


class UpdateFlagRequest(BaseModel):
    """Patch a flag: toggle `enabled` and/or replace its `payload` (e.g.
    `geo_config`'s excluded-state list). At least one field must be present."""

    enabled: bool | None = None
    payload: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #


class AdminUserSummary(BaseModel):
    """A row in the users table (search results / list)."""

    id: UUID
    username: str | None
    email: str | None
    friend_code: str
    role: str
    status: str
    residence_state: str | None
    member_since: datetime
    available_cents: int
    escrow_cents: int


class AdminUserListResponse(BaseModel):
    users: list[AdminUserSummary]


class AdminLinkedAccount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game: str
    host_username: str
    host_account_id: str
    link_method: str
    status: str


class AdminLimits(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    daily_loss_cap_cents: int
    daily_entry_cap_cents: int
    max_concurrent_contests: int


class AdminContestRow(BaseModel):
    """A contest the user took part in (unified across match/pool/tournament)."""

    ref_type: str
    ref_id: UUID
    game: str
    market: str
    state: str
    entry_cents: int
    payout_cents: int
    created_at: datetime
    resolved_at: datetime | None


class AdminUserDetail(BaseModel):
    id: UUID
    auth_id: str
    username: str | None
    email: str | None
    friend_code: str
    role: str
    status: str
    residence_state: str | None
    dob_attested_18plus: bool
    member_since: datetime
    last_seen_at: datetime | None
    available_cents: int
    escrow_cents: int
    lifetime_net_cents: int
    limits: AdminLimits | None
    linked_accounts: list[AdminLinkedAccount]
    contests: list[AdminContestRow]
    recent_ledger: list[LedgerEntryResponse]


class AdjustRequest(BaseModel):
    """Manual ledger adjustment. Signed cents (credit/debit); reason required."""

    amount_cents: int = Field(..., description="Signed cents; positive credits.")
    reason: str = Field(..., min_length=1)


class ActionResult(BaseModel):
    """Generic confirmation for a mutating admin action."""

    ok: bool = True
    status: str | None = None


class AdminLedgerPage(BaseModel):
    entries: list[LedgerEntryResponse]
    next_cursor: str | None


# --------------------------------------------------------------------------- #
# Contests
# --------------------------------------------------------------------------- #


class AdminContestListItem(BaseModel):
    ref_type: str
    ref_id: UUID
    game: str
    market: str
    state: str
    entry_cents: int
    pot_cents: int
    participants: int
    created_at: datetime
    resolved_at: datetime | None


class AdminContestListResponse(BaseModel):
    contests: list[AdminContestListItem]


class AdminContestDetail(BaseModel):
    ref_type: str
    ref_id: UUID
    game: str
    market: str
    state: str
    entry_cents: int
    pot_cents: int
    prize_cents: int
    rake_cents: int
    engine_version: str | None
    outcome_detail: dict[str, Any] | None
    created_at: datetime
    resolved_at: datetime | None
    participants: list[dict[str, Any]]
    ledger: list[dict[str, Any]]
    platform_ledger: list[dict[str, Any]]
    reconciliation: dict[str, Any]


class VoidRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class ResettleResult(BaseModel):
    outcome: str
    state: str


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #


class QueueDepthRow(BaseModel):
    game: str
    market: str
    entry_cents: int
    waiting: int
    avg_wait_seconds: float


class QueueResponse(BaseModel):
    waiting: int
    matched: int
    expired: int
    canceled: int
    expiry_rate: float
    depth: list[QueueDepthRow]


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #


class ReconViolationRow(BaseModel):
    ref_type: str
    ref_id: UUID
    violations: list[str]
    totals: dict[str, int]


class WorkerStatus(BaseModel):
    heartbeat_at: datetime | None
    stale: bool


class ReconciliationResponse(BaseModel):
    ok: bool
    solvency_ok: bool
    solvency_violations: list[str]
    totals: dict[str, int]
    contest_violations: list[ReconViolationRow]
    worker: WorkerStatus


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #


class RiskRateRow(BaseModel):
    game: str
    market: str
    offered: int
    accepted: int
    settled: int
    expected_rate: float | None
    actual_rate: float | None
    rake_cents: int
    dispute_count: int
    alert: bool


class RiskFlagRow(BaseModel):
    id: UUID
    user_id: UUID
    username: str | None
    game: str
    metric: str
    kind: str
    detail: dict[str, Any]
    created_at: datetime


class RiskResponse(BaseModel):
    rates: list[RiskRateRow]
    flags: list[RiskFlagRow]
