"""Solo-pool wire types (07-phase-4). Ids + preset choices only on the way in;
every bar, room bar, and payout is server-derived on the way out."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DifficultyCard(BaseModel):
    """One difficulty quoted from the viewer's own baseline (design PDF p.4)."""

    difficulty: str
    bar: float  # your personal bar = round(μ + k·σ)
    clear_rate: float  # disclosed difficulty 1 − Φ(k), NOT an odds line
    est_multiplier_bps: int  # estimated share-of-pool multiplier (display only)


class PoolMetric(BaseModel):
    metric: str
    label: str
    provisional: bool
    cards: list[DifficultyCard]


class PoolMarketsResponse(BaseModel):
    game: str
    linked: bool
    entry_presets_cents: list[int]
    metrics: list[PoolMetric]


class PoolEnterRequest(BaseModel):
    """Enter a pool = enqueue. Ids + preset only — no bar, no amount."""

    game: str
    metric: str
    difficulty: str
    entry_preset_cents: int


class PoolMemberView(BaseModel):
    user_id: UUID
    username: str | None
    personal_bar: float
    status: str
    payout_cents: int
    is_you: bool


class PoolView(BaseModel):
    id: UUID
    game: str
    metric: str
    metric_label: str
    difficulty: str
    room_bar: float
    your_bar: float | None
    bar_delta: float | None  # room_bar − your_bar (shown on the room card)
    entry_cents: int
    pot_cents: int
    prize_cents: int
    rake_cents: int
    room_size: int
    state: str
    window_starts_at: datetime
    window_ends_at: datetime
    members: list[PoolMemberView]
    your_payout_cents: int | None
    resolved_at: datetime | None


class PoolStatusResponse(BaseModel):
    status: str  # idle | searching | formed
    pool: PoolView | None = None
    difficulty: str | None = None
    metric: str | None = None
    waited_seconds: int | None = None


class PoolsListResponse(BaseModel):
    """The "Open pools" surface: your in-flight rooms + queue state."""

    status: PoolStatusResponse
    rooms: list[PoolView]
