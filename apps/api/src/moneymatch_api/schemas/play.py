"""`Bracket` and `Forecast` are the honest, no-odds pairing disclosures shown on the
matched card ("Even duel — model gives you 52%"), the P2P analog of rake
disclosure.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Bracket(BaseModel):
    """How fair a chess pairing is, for honest pre-match disclosure (Elo-based)."""

    your_rating: int
    band_low: int
    band_high: int
    match_quality: float
    label: str


class Forecast(BaseModel):
    you_win_prob: float
    label: str


class MarketRow(BaseModel):
    """One market row on the Play screen."""

    key: str
    label: str
    kind: str
    requires_speed: bool
    speeds: list[str]
    # Derived pot multiplier in basis points (2·(1 − rake)); NEVER an odds line.
    multiplier_bps: int
    queue_depth: int
    resolution_note: str


class MarketsResponse(BaseModel):
    game: str
    linked: bool
    entry_presets_cents: list[int]
    markets: list[MarketRow]


class QueueRequest(BaseModel):
    """Join the queue."""

    game: str
    market: str
    speed: str | None = None
    entry_preset_cents: int


class MatchPlayerView(BaseModel):
    user_id: UUID
    username: str | None
    rating: int | None
    color: str | None
    confirmed: bool
    payout_cents: int
    stat_line: dict | None
    is_you: bool


class MatchView(BaseModel):
    """A match as one participant sees it (design's matched / active slip)."""

    id: UUID
    game: str
    market: str
    market_label: str
    kind: str
    speed: str | None
    entry_cents: int
    pot_cents: int
    prize_cents: int
    rake_cents: int
    multiplier_bps: int
    state: str
    host_game_id: str | None
    matched_at: datetime | None
    window_ends_at: datetime | None
    players: list[MatchPlayerView]
    you_confirmed: bool
    your_play_url: str | None
    forecast: Forecast | None
    # How the game ended (checkmate | resignation | time | draw | stalemate |
    # abandoned | aborted | other), when Lichess said so.
    termination: str | None = None
    # When the game ended on Lichess, and when we settled it; null when unknown.
    game_ended_at: datetime | None = None
    resolved_at: datetime | None = None
    # The viewer-oriented board (moves, clocks, turn, result); null when stale or
    # unavailable.
    live: dict | None = None


class GradingExplanation(BaseModel):
    """ "Why this result" — the transparent grading record for a contest the viewer
    was in: the rule, what each side produced, and the decision.
    """

    match_id: UUID
    state: str
    settled: bool
    result: str
    market_label: str
    rule: str
    engine_version: str | None
    resolved_at: datetime | None
    winner_username: str | None
    your_stat_line: dict | None
    opponent_stat_line: dict | None
    outcome_detail: dict | None


class FileDisputeRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class ContestRequest(BaseModel):
    """File a dispute against any contest type (match | pool | tournament)."""

    ref_type: str = Field(..., pattern="^(match|pool|tournament)$")
    ref_id: UUID
    reason: str = Field(..., min_length=1, max_length=1000)


class DisputeView(BaseModel):
    """A dispute as its filer sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ref_type: str
    ref_id: UUID
    reason: str
    status: str
    admin_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class QueueStatusResponse(BaseModel):
    """Where the viewer stands: idle, searching (with wait), or matched."""

    status: str
    match: MatchView | None = None
    waited_seconds: int | None = None
    can_cancel: bool = True


class WaitingRow(BaseModel):
    """An open ticket of another player (design's "Waiting to play" list)."""

    ticket_id: UUID
    game: str
    market: str
    market_label: str
    speed: str | None
    entry_cents: int
    username: str | None
    rating: int | None
    waited_seconds: int


class WaitingResponse(BaseModel):
    waiting: list[WaitingRow]


class ActivityItem(BaseModel):
    """One row in the unified Activity feed (H2H matches, pools, tournaments)."""

    type: str
    id: UUID
    game: str
    market: str
    market_label: str
    kind: str
    state: str
    entry_cents: int
    title: str | None = None
    # Your realized net once resolved (+prize−entry on a win, −entry on a loss, 0 on
    # push/refund); null while the match is still in flight.
    net_cents: int | None
    opponent_username: str | None
    your_stat_line: dict | None
    opponent_stat_line: dict | None
    live: dict | None = None
    detail: dict | None = None
    dispute_status: str | None = None
    created_at: datetime
    resolved_at: datetime | None


class ActivityResponse(BaseModel):
    items: list[ActivityItem]
