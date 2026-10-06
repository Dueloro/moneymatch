"""Tournament wire types. Ids + preset in; server-derived scores, ranks, payouts
and per-game verdicts out."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OpenTable(BaseModel):
    """How many players are already in the open tournament at one entry."""

    entry_cents: int
    players: int


class TournamentMetric(BaseModel):
    metric: str
    label: str
    # Kept for older clients; always False now (anyone linked can join).
    provisional: bool
    # One-line rules for the card, e.g. "Best of your first 3 official matches".
    rules: str
    open_tables: list[OpenTable] = []


class TournamentMarketsResponse(BaseModel):
    game: str
    linked: bool
    entry_presets_cents: list[int]
    prize_split: list[int]  # relative weights, e.g. [60, 25, 15]
    field_size: int  # the most players one tournament takes
    min_players: int
    score_matches: int
    join_window_seconds: int
    duration_seconds: int
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


class TournamentGame(BaseModel):
    """One of your games around the tournament, and whether/why it counted."""

    host_match_id: str
    started_at: datetime
    ended_at: datetime | None
    mode: str | None
    result: str | None
    reason: str  # COUNTED, TOO_SHORT, WRONG_MODE, …
    reason_text: str
    value: float | None  # points (chess) or the stat, when it counted


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
    players: int
    score_matches: int
    state: str
    # Null while waiting for a second player (the clock hasn't started).
    window_starts_at: datetime | None
    window_ends_at: datetime | None
    join_closes_at: datetime | None
    your_entered_at: datetime | None
    # Anonymized field fairness: the μ spread ("Field: K/D 1.42–1.58").
    field_mu_low: float | None
    field_mu_high: float | None
    standings: list[StandingRow]
    your_rank: int | None
    your_payout_cents: int | None
    your_games: list[TournamentGame] = []
    outcome_reason: str | None = None
    resolved_at: datetime | None


class TournamentStatusResponse(BaseModel):
    status: str  # idle | searching | formed
    tournament: TournamentView | None = None
    metric: str | None = None
    waited_seconds: int | None = None


class TournamentsListResponse(BaseModel):
    status: TournamentStatusResponse
    tournaments: list[TournamentView]
