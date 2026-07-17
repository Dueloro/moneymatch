"""Tournament wire types (07-phase-4). Ids + preset in; server-derived scores,
ranks, and payouts out. The field's μ-spread is *displayed* fairness, not odds."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TournamentMetric(BaseModel):
    metric: str
    label: str
    provisional: bool


class TournamentMarketsResponse(BaseModel):
    game: str
    linked: bool
    entry_presets_cents: list[int]
    prize_split: list[int]  # relative weights, e.g. [50, 30, 20]
    field_size: int
    score_matches: int
    metrics: list[TournamentMetric]


class TournamentEnterRequest(BaseModel):
    game: str
    metric: str
    entry_preset_cents: int


class StandingRow(BaseModel):
    user_id: UUID
    username: str | None
    score: float | None
    matches: int
    rank: int | None
    is_you: bool
    payout_cents: int


class TournamentView(BaseModel):
    id: UUID
    game: str
    metric: str
    metric_label: str
    entry_cents: int
    pot_cents: int
    prize_cents: int
    rake_cents: int
    prize_split: list[int]
    field_size: int
    score_matches: int
    state: str
    window_starts_at: datetime
    window_ends_at: datetime
    # Anonymized field fairness: the μ spread ("Field: K/D 1.42–1.58").
    field_mu_low: float | None
    field_mu_high: float | None
    standings: list[StandingRow]
    your_rank: int | None
    your_payout_cents: int | None
    resolved_at: datetime | None


class TournamentStatusResponse(BaseModel):
    status: str  # idle | searching | formed
    tournament: TournamentView | None = None
    metric: str | None = None
    waited_seconds: int | None = None


class TournamentsListResponse(BaseModel):
    status: TournamentStatusResponse
    tournaments: list[TournamentView]
