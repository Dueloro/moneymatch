"""Request/response models for the `/bucketing` API surface (the wiring)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class MarketCard(BaseModel):
    game: str
    mode: str
    metric: str
    label: str
    placed: bool
    bucket: int | None = None
    bar: float | None = None
    stake_cap_cents: int | None = None  # None = uncapped
    provisional: bool = True
    multiplier_bps: int = 0


class MarketsResponse(BaseModel):
    enabled: bool
    markets: list[MarketCard]


class WagerRequest(BaseModel):
    game: str
    mode: str
    metric: str
    stake_cents: int = Field(gt=0)


class ContestStatus(BaseModel):
    contest_id: UUID
    game: str
    mode: str
    metric: str
    bucket: int
    status: str
    stake_cents: int
    bar: float | None = None
    result_value: float | None = None
    cleared: bool | None = None
    payout_cents: int
    room_id: UUID | None = None


class DisputeRequest(BaseModel):
    contest_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


class DisputeResponse(BaseModel):
    dispute_id: UUID
    status: str
    hold: bool


class ResolveRequest(BaseModel):
    #: no_change | refund | clawback
    resolution: str
    note: str | None = None
    #: Required for a clawback: the player(s) found to have been unfair.
    fault_player_ids: list[UUID] = []
