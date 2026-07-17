"""Play schemas: the pairing disclosures plus the `/play/*` + `/activity` wire types.

`Bracket` and `Forecast` are the honest, no-odds pairing disclosures shown on the
matched card ("Even duel — model gives you 52%"), the P2P analog of rake
disclosure (06-phase-3 · deliverable 2). Requests carry **ids/presets only** —
never amounts or timestamps (00-README §3); the server owns every number.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Bracket(BaseModel):
    """How fair a chess pairing is, for honest pre-match disclosure (Elo-based)."""

    your_rating: int
    band_low: int
    band_high: int
    match_quality: float  # 1.0 at a coin-flip, decays as the matchup gets lopsided
    label: str


class Forecast(BaseModel):
    """The duel-forecast disclosure for a stat/chess pairing.

    `you_win_prob` is `P(you beat opponent)` from the model (held near 0.50 by
    the eligibility window); `label` is the honest one-liner for the matched card.
    """

    you_win_prob: float
    label: str


# --- markets -------------------------------------------------------------- #


class MarketRow(BaseModel):
    """One market row on the Play screen (design PDF p.1)."""

    key: str
    label: str
    kind: str  # win_h2h | win_next | stat_race
    metric: str | None
    requires_speed: bool
    speeds: list[str]  # chess time controls (empty for other games)
    # Derived pot multiplier in basis points (2·(1 − rake)); NEVER an odds line.
    multiplier_bps: int
    queue_depth: int  # players currently waiting on this market
    provisional: bool  # the viewer can't duel this stat yet (n below the floor)
    resolution_note: str  # honest one-liner on how it settles (+ forfeit rule)


class MarketsResponse(BaseModel):
    game: str
    linked: bool  # whether the viewer has linked this game
    entry_presets_cents: list[int]
    markets: list[MarketRow]


# --- queue / match -------------------------------------------------------- #


class QueueRequest(BaseModel):
    """Join the queue. Ids + a server preset only — no amounts, no timestamps."""

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
    brokered: bool
    host_game_id: str | None
    matched_at: datetime | None
    window_ends_at: datetime | None
    players: list[MatchPlayerView]
    you_confirmed: bool
    your_play_url: str | None
    forecast: Forecast | None  # honest matched-card disclosure, from your view


class QueueStatusResponse(BaseModel):
    """Where the viewer stands: idle, searching (band + wait), or matched."""

    status: str  # idle | searching | matched
    match: MatchView | None = None
    waited_seconds: int | None = None
    tolerance_stage: int | None = None
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


# --- activity ------------------------------------------------------------- #


class ActivityItem(BaseModel):
    """One row in the unified Activity feed (H2H matches, pools, tournaments)."""

    type: str  # "match" | "pool" | "tournament"
    id: UUID
    game: str
    market: str
    market_label: str
    kind: str
    state: str
    entry_cents: int
    # Pool/tournament rows supply a title (matches build theirs from opponent).
    title: str | None = None
    # Your realized net once resolved (+prize−entry on a win, −entry on a loss,
    # 0 on push/refund); null while the match is still in flight.
    net_cents: int | None
    opponent_username: str | None
    your_stat_line: dict | None
    opponent_stat_line: dict | None
    created_at: datetime
    resolved_at: datetime | None


class ActivityResponse(BaseModel):
    items: list[ActivityItem]
