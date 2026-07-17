"""Pydantic models for money match's Phase 1 API surface.

Phase 1 is **peer-to-peer head-to-head**: two players stake an equal entry into
an escrowed pot, play one qualifying game, and the winner takes the pot minus a
fixed platform rake (roadmap §1, overview §2). The platform never sets a payout
line and never takes a position — it matches players and collects the rake.

In the play-money demo the opponent is a skill-bracketed bot (overview §8.1,
roadmap §1.5); the shapes are the ones the production DB will store, so a real
second player drops into the same `Opponent` slot later.

These shapes mirror the TypeScript types in ``src/types``; they are flat and
JSON-friendly so the same objects round-trip between the Python serverless
functions and the React client (which persists them to localStorage).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Identity / skill profile
# ---------------------------------------------------------------------------

# Lichess time controls money match runs contests for.
Speed = Literal["bullet", "blitz", "rapid", "classical"]

# How an account was linked. OAuth is the production path; "username" is the
# play-money demo path (public stats only) — see roadmap §1.1 "Identity".
LinkMethod = Literal["oauth", "username"]


class FormatStat(BaseModel):
    """A single time-control's verified stats, sourced from the host API."""

    speed: Speed
    rating: int
    games: int
    provisional: bool = False


class SkillProfile(BaseModel):
    """Verified, host-derived skill profile that drives matchmaking/bracketing.

    Chess populates the per-format / ``primary_speed`` fields; other titles
    (e.g. FaceIt CS2) leave those empty and use the generic ``rating`` /
    ``rank_label`` / ``kd`` descriptors instead. ``game`` is the adapter id."""

    username: str
    display_name: str
    url: str
    link_method: LinkMethod
    game: str = "chess.lichess"
    account_age_days: Optional[int] = None
    # Overall record across the user's history (a soft signal for bracketing).
    win_rate: float            # (wins + 0.5*draws) / total, 0..1
    draw_rate: float = 0.0     # draws / total, 0..1 (chess; 0 where N/A)
    total_games: int
    # Chess-specific (empty for other titles).
    formats: list[FormatStat] = []
    primary_speed: Optional[Speed] = None
    # Generic skill descriptors usable by any title.
    rating: Optional[int] = None        # elo / mmr / faceit_elo
    rank_label: Optional[str] = None    # e.g. "Level 10", "Diamond II"
    kd: Optional[float] = None          # average kill/death ratio (FPS)
    avatar_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Objectives (the "what decides the contest" of a head-to-head)
# ---------------------------------------------------------------------------

ObjectiveKind = Literal[
    "win_h2h",          # win the head-to-head qualifying game
    "win_under_moves",  # win the head-to-head game in under N moves
]


class Objective(BaseModel):
    """A typed, parameterized objective. Builder and Lobby emit this shape.

    Phase 1 ships the two head-to-head families; multi-entrant tournament
    objectives are a Phase 2 addition (roadmap §3).
    """

    kind: ObjectiveKind
    # win_under_moves only.
    moves: Optional[int] = None


# ---------------------------------------------------------------------------
# Matchmaking: bracket + opponent (replace the deprecated house-banked Line)
# ---------------------------------------------------------------------------


class Bracket(BaseModel):
    """How fair the pairing is. Matchmaking creates fairness, not odds."""

    your_rating: int
    band_low: int
    band_high: int
    match_quality: float    # 0..1; 1.0 == dead-even pairing
    label: str              # "Even match" / "You're favored" / "Reach" / …


class Opponent(BaseModel):
    """The matched counterparty. A skill-bracketed bot in the demo."""

    username: str
    display_name: str
    rating: int
    is_bot: bool = True


# ---------------------------------------------------------------------------
# Contracts (a peer-to-peer head-to-head contest)
# ---------------------------------------------------------------------------

ContractState = Literal[
    "OPEN",       # listed in the lobby; no entry committed
    "MATCHED",    # opponent confirmed; entries escrowed
    "ACTIVE",     # qualifying game underway
    "RESOLVING",  # game done; confirming via host API
    "SETTLED",    # outcome verified; pot paid minus rake
    "CANCELED",   # no qualifying game / abort / outage — entries refunded
]
ContractOutcome = Literal["won", "lost", "refunded"]
Winner = Literal["you", "opponent"]


class ContractDraft(BaseModel):
    """A pre-matched contest request (from the Builder or Lobby generator)."""

    game: str = "chess.lichess"   # adapter id
    speed: str                    # chess time control ("blitz") or a game mode ("cs2")
    format: str                   # human label, e.g. "Rated Blitz"
    objective: Objective
    window_hours: int = 6
    entry: float = 5.0            # per-player stake


class Contract(BaseModel):
    """A fully-built head-to-head contest. ``state`` advances OPEN → SETTLED.

    Pot economics: ``pot = entry * entrants``; the winner receives
    ``prize = pot * (1 - rake_pct)`` and money match keeps ``rake = pot - prize``.
    Invariant at settlement: payout(winner) + rake == pot (overview §7.1).
    """

    id: str
    game: str
    speed: str                    # chess time control or game mode (e.g. "cs2")
    format: str
    title: str                    # short human summary, e.g. "Win the blitz match"
    objective: Objective
    window_hours: int
    account_id: Optional[str] = None  # the linked account this settles against

    # Money (escrow + rake — never an odds line).
    entry: float
    entrants: int = 2
    rake_pct: float
    pot: float
    prize: float                  # what the winner receives
    rake: float                   # what money match keeps

    # Matchmaking.
    bracket: Bracket
    opponent: Opponent

    state: ContractState = "OPEN"
    matched_at: Optional[float] = None     # epoch ms (when entries escrowed)
    resolved_at: Optional[float] = None    # epoch ms
    qualifying_game_ids: list[str] = []
    progress: Optional[str] = None         # e.g. "Awaiting your next blitz game"
    winner: Optional[Winner] = None
    outcome: Optional[ContractOutcome] = None


# ---------------------------------------------------------------------------
# Real head-to-head matchmaking (roadmap Phase 1)
# ---------------------------------------------------------------------------
#
# Two real players are paired by a server-side queue, both stake, play ONE real
# game against each other, and the winner is paid — no bot. The integrity anchor:
# settlement grades the single host match that contains BOTH accounts. Chess is
# "brokered" (the server creates a Lichess open challenge and hands each player a
# color URL); CS2/Dota are "coordinated" (players add each other, and we settle
# on the shared match found in their histories).

MatchState = Literal[
    "PENDING",    # matched; awaiting both players' confirmation
    "ACTIVE",     # both confirmed + escrowed; game is on (brokered id or coordinated)
    "SETTLED",    # the shared match resolved; winner paid pot − rake
    "CANCELED",   # declined / expired / drawn — entries refunded
]


class MatchPlayer(BaseModel):
    player_id: str                    # linked account (the settlement key)
    display_name: str
    rating: int
    color: Optional[str] = None       # brokered chess: "white" | "black"
    confirmed: bool = False
    play_url: Optional[str] = None    # brokered game URL for this player
    payout: float = 0.0               # credited on settlement (prize / refund)


class Match(BaseModel):
    """A real two-player head-to-head, owned by the server-side queue."""

    id: str
    game: str
    speed: str
    format: str
    entry: float
    rake_pct: float
    pot: float
    prize: float
    rake: float
    brokered: bool                    # True ⇒ platform creates the game (chess)
    players: list[MatchPlayer]        # exactly two
    state: MatchState = "PENDING"
    host_game_id: Optional[str] = None  # brokered game id (chess)
    winner_id: Optional[str] = None
    outcome: Optional[str] = None      # "settled" | "refunded"
    progress: Optional[str] = None
    created_at: float
    matched_at: Optional[float] = None
    resolved_at: Optional[float] = None


class QueueRequest(BaseModel):
    player_id: str
    display_name: str
    game: str
    speed: str
    format: str
    entry: float
    rating: int = 1500


class QueueResponse(BaseModel):
    status: str                        # "searching" | "matched" | "idle"
    match: Optional[Match] = None


class MatchActionRequest(BaseModel):
    match_id: str
    player_id: str


# ---------------------------------------------------------------------------
# API request/response envelopes
# ---------------------------------------------------------------------------


class LobbyResponse(BaseModel):
    profile: SkillProfile
    contests: list[Contract]


class PriceRequest(ContractDraft):
    """Body for POST /api/contracts/price — a draft to match + price."""


class SettleRequest(BaseModel):
    """Body for POST /api/contracts/settle.

    The demo keeps contract state on the client; settlement is server-authoritative
    grading against the user's real games. The client sends its in-flight contests
    and the server returns the ones that changed.
    """

    username: str
    contracts: list[Contract]


class SettleResult(BaseModel):
    id: str
    state: ContractState
    outcome: Optional[ContractOutcome] = None
    winner: Optional[Winner] = None
    qualifying_game_ids: list[str] = []
    progress: Optional[str] = None
    resolved_at: Optional[float] = None
    payout: float = 0.0           # credited to the user (prize on win, entry on refund)


class SettleResponse(BaseModel):
    results: list[SettleResult]


# ---------------------------------------------------------------------------
# Algorithmic Solo Challenges — POOLED solo tournament (overview §10)
# ---------------------------------------------------------------------------
#
# Players each pay an entry fee into a shared pool for a given game + qualifying
# standard. Everyone plays their own game; the platform verifies API telemetry
# against the standard (a measurable metric, never a win/loss or prediction).
# Entrants who CLEAR the standard split the pool MINUS a fixed platform rake.
#
# There is NO house: the prize comes entirely from entrants' pooled fees, the
# platform never funds a prize and holds no outcome position. Invariant at
# settlement: ``sum(payouts) + rake == sum(entries)`` — identical to the P2P
# escrow/rake model (overview §2 / §7.1). This is the legally compliant,
# neutral-operator structure; play-money in the demo.

SoloGame = Literal[
    "rocketleague.psyonix",
    "clashroyale.supercell",
    "chess.lichess",
    "cs2.faceit",
    "dota2.opendota",
]

# A measurable, player-controlled performance metric. Prop-betting metrics (pure
# time predictions, etc.) are banned by policy (overview §10 guardrails).
MetricKind = Literal[
    "rl_aerial_accuracy_pct",   # Rocket League: % of aerial hits on target
    "rl_match_score",           # Rocket League: in-match score points
    "cr_crown_tower_damage",    # Clash Royale: total crown-tower damage dealt
    "chess_accuracy_pct",       # Chess: Stockfish accuracy % over the game
    "cs2_kills",                # CS2: kills over the match
    "cs2_kd_ratio",             # CS2: kill/death ratio over the match
    "cs2_headshot_pct",         # CS2: headshot % over the match
    "cs2_adr",                  # CS2: average damage per round (contribution standard)
    "cs2_mvps",                 # CS2: MVP rounds earned over the match
    "dota2_kda_ratio",          # Dota 2: (kills+assists)/deaths over the match
    "dota2_gpm",                # Dota 2: gold per minute over the match
]

Comparator = Literal["gte", "lte"]


class MetricTarget(BaseModel):
    """The qualifying standard an entrant must clear.

    ``metric`` compared via ``comparator`` against ``threshold``. An optional
    secondary constraint expresses compound standards (e.g. Clash Royale:
    "4,000+ crown-tower damage using <30 total elixir" or Chess: "≥82% accuracy
    over ≥20 moves").
    """

    metric: MetricKind
    comparator: Comparator
    threshold: float
    # Optional compound constraint, e.g. {"metric": "cr_total_elixir",
    # "comparator": "lte", "threshold": 30} or a minimum-moves gate for chess.
    secondary_metric: Optional[str] = None
    secondary_comparator: Optional[Comparator] = None
    secondary_threshold: Optional[float] = None


class TelemetrySample(BaseModel):
    """Mock game telemetry posted to the verification webhook."""

    game: SoloGame
    metrics: dict[str, float]     # e.g. {"rl_aerial_accuracy_pct": 71.5, "rl_match_score": 640}


SoloEntryStatus = Literal[
    "LOCKED",          # entry escrowed into the pool, awaiting play + telemetry
    "CLEARED",         # standard met — shares the post-rake pool
    "MISSED",          # standard not met — entry stays in the pool for clearers
    "REFUNDED",        # pool canceled / no clearers — entry returned
    "BLOCKED_REGION",  # geo-fenced state — never entered/charged
]

SoloPoolStatus = Literal[
    "OPEN",       # accepting entrants
    "SETTLED",    # graded; pool distributed to clearers minus rake
    "CANCELED",   # below min entrants — all entries refunded, no rake
]


class SoloEntry(BaseModel):
    """One player's stake in a pooled solo tournament."""

    player_id: str
    state: str                    # residence state (for the geo-check)
    status: SoloEntryStatus = "LOCKED"
    cleared: Optional[bool] = None
    payout: float = 0.0           # share of the pool credited on settlement
    detail: Optional[str] = None


class SoloPool(BaseModel):
    """A pooled solo tournament: shared prize pool, rake-only, no house."""

    id: str
    game: SoloGame
    metric_target: MetricTarget
    entry_fee: float              # equal stake every entrant pays
    rake_pct: float
    min_entrants: int = 2         # below this the pool cancels + refunds
    entrants: list[SoloEntry] = []
    pool: float = 0.0             # sum of all entries
    rake: float = 0.0             # taken only when a prize is actually distributed
    prize_pool: float = 0.0       # pool - rake, split among clearers
    status: SoloPoolStatus = "OPEN"
    created_at: Optional[float] = None
    resolved_at: Optional[float] = None


class SoloPoolCreate(BaseModel):
    """Body for POST /api/solo/pools — open a pooled tournament."""

    game: SoloGame
    metric_target: MetricTarget
    entry_fee: float = 5.0
    rake_pct: float = 0.10
    min_entrants: int = 2


class SoloEnterRequest(BaseModel):
    """Body for POST /api/solo/pools/enter — join a pool (geo-fenced)."""

    pool: SoloPool
    player_id: str
    state: str                    # player's residence state (for the geo-fence)


class SoloSettleRequest(BaseModel):
    """Body for POST /api/solo/pools/settle — grade + distribute the pool.

    ``telemetry`` maps each entrant's ``player_id`` to their game telemetry.
    """

    pool: SoloPool
    telemetry: dict[str, TelemetrySample]


class SoloLobbyResponse(BaseModel):
    """Open pooled solo tournaments a player can join (GET /api/solo/lobby)."""

    pools: list[SoloPool]


# ---------------------------------------------------------------------------
# Multi-entrant tournaments (roadmap §3 — Phase 2)
# ---------------------------------------------------------------------------
#
# N players each pay an equal entry into a shared prize pool, play their
# qualifying game(s), and are RANKED by an objective metric. The top finishers
# split ``pool − rake`` per a fixed ``prize_split`` (e.g. 60/30/10). This is the
# same neutral-operator escrow/rake model as the head-to-head and solo sides —
# the platform never funds a prize and holds no outcome position. Invariant at
# settlement: ``sum(payouts) + rake == sum(entries)`` (overview §2 / §7.1).
#
# ``leaderboard_pool`` is the shipping format (ranked pool, top-N paid).
# ``single_elim`` is reserved for the bracketed head-to-head chains that build
# on the Phase 1 H2H primitive (next iteration). Play-money in the demo.

TournamentFormat = Literal[
    "leaderboard_pool",   # N entrants ranked by a metric; top finishers split the pool
    "single_elim",        # bracketed H2H chain (reserved — next iteration)
]

TournamentStatus = Literal[
    "OPEN",       # accepting entrants
    "SETTLED",    # graded; pool distributed to top finishers minus rake
    "CANCELED",   # below min entrants — all entries refunded, no rake
]

TournamentEntryStatus = Literal[
    "LOCKED",     # entry escrowed, awaiting play + telemetry
    "PAID",       # finished in the money — took a prize_split share
    "OUT",        # finished out of the money — entry funds the prizes
    "REFUNDED",   # tournament canceled / un-verifiable result — entry returned
]


class TournamentEntry(BaseModel):
    """One player's stake + result in a tournament."""

    player_id: str
    state: str                    # residence state (for the geo-check)
    status: TournamentEntryStatus = "LOCKED"
    score: Optional[float] = None  # ranking-metric value (None ⇒ un-verifiable);
                                   # for single_elim this is the player's match strength
    rank: Optional[int] = None     # final placement, 1 == winner
    payout: float = 0.0           # prize share / refund credited on settlement
    detail: Optional[str] = None


class BracketMatch(BaseModel):
    """One head-to-head match in a single-elimination bracket.

    ``player_a``/``player_b`` are ``player_id``s, or ``None`` for a bye/empty
    slot. A drawn game triggers a rematch (same pairing) until decisive, so
    ``games`` counts every game played including replays (draw policy: rematch).
    """

    round: int                    # 0 == first round
    slot: int                     # position within the round
    player_a: Optional[str] = None
    player_b: Optional[str] = None
    winner: Optional[str] = None  # the player_id that advanced
    games: int = 0                # games played (>1 means draws forced rematches)
    detail: Optional[str] = None


class Tournament(BaseModel):
    """A multi-entrant ranked tournament: shared pool, rake-only, no house."""

    id: str
    game: SoloGame
    name: str                     # short human label, e.g. "Blitz Accuracy Open"
    format: TournamentFormat = "leaderboard_pool"
    ranking_metric: MetricKind    # entrants are ranked on this metric
    higher_is_better: bool = True
    entry_fee: float              # equal stake every entrant pays
    rake_pct: float
    max_entrants: int             # cap; the lobby seeds bots to one short of this
    min_entrants: int = 2         # below this the tournament cancels + refunds
    # Top-N prize weights (sum ~1.0), e.g. [0.6, 0.3, 0.1]. Renormalized if fewer
    # ranked entrants than paid places exist, so the net pool is fully paid out.
    prize_split: list[float]
    entrants: list[TournamentEntry] = []
    pool: float = 0.0             # sum of all entries
    rake: float = 0.0             # taken only when prizes are actually distributed
    prize_pool: float = 0.0       # pool - rake, split among the top finishers
    # single_elim only: the played-out bracket, one list of matches per round
    # (round 0 first). Empty for leaderboard_pool and until settlement.
    rounds: list[list[BracketMatch]] = []
    status: TournamentStatus = "OPEN"
    created_at: Optional[float] = None
    resolved_at: Optional[float] = None


class TournamentCreate(BaseModel):
    """Body for POST /api/tournaments — open a tournament."""

    game: SoloGame
    name: str
    ranking_metric: MetricKind
    higher_is_better: bool = True
    format: TournamentFormat = "leaderboard_pool"
    entry_fee: float = 5.0
    rake_pct: float = 0.10
    max_entrants: int = 8
    min_entrants: int = 2
    prize_split: list[float] = [0.6, 0.3, 0.1]


class TournamentEnterRequest(BaseModel):
    """Body for POST /api/tournaments/enter — join a tournament (geo-fenced)."""

    tournament: Tournament
    player_id: str
    state: str                    # player's residence state (for the geo-fence)


class TournamentSettleRequest(BaseModel):
    """Body for POST /api/tournaments/settle — rank + distribute the pool.

    ``telemetry`` maps each entrant's ``player_id`` to their game telemetry.
    """

    tournament: Tournament
    telemetry: dict[str, TelemetrySample]


class TournamentLobbyResponse(BaseModel):
    """Open tournaments a player can join (GET /api/tournaments/lobby)."""

    tournaments: list[Tournament]


# ---------------------------------------------------------------------------
# Leaderboard (roadmap §3 — Phase 2 retention surface)
# ---------------------------------------------------------------------------
#
# Ranked by **record / ROI, never raw $ won** (overview/roadmap §3.1 — avoids
# pay-to-play optics where the biggest bankroll tops the board). In the demo the
# server seeds a field of bot players; the client merges in the signed-in user's
# own demo record and re-ranks by ROI.


class LeaderboardEntry(BaseModel):
    """One ranked competitor's record across contests."""

    player_id: str
    display_name: str
    is_bot: bool = True
    contests: int                 # graded (non-refunded) contests played
    wins: int                     # H2H wins + in-the-money finishes
    win_rate: float               # wins / contests, 0..1
    staked: float                 # total entries across graded contests
    net: float                    # net profit/loss (can be negative)
    roi: float                    # net / staked, the primary ranking key


class LeaderboardResponse(BaseModel):
    """Seeded competitive field (GET /api/leaderboard), best ROI first."""

    entries: list[LeaderboardEntry]


# ---------------------------------------------------------------------------
# Spectator view (roadmap §3 — watch your own active match)
# ---------------------------------------------------------------------------
#
# A move list + clock for the signed-in user's *current* Lichess game (the §3.4
# lower-fidelity option vs. a full board stream). Sourced live from the public
# Lichess "current game" endpoint; un-available when the user isn't playing.


class SpectatePlayer(BaseModel):
    name: str
    rating: Optional[int] = None


class SpectateResponse(BaseModel):
    available: bool                       # False when the user has no current game
    game_id: Optional[str] = None
    url: Optional[str] = None
    speed: Optional[str] = None           # "blitz", "rapid", …
    white: Optional[SpectatePlayer] = None
    black: Optional[SpectatePlayer] = None
    moves: list[str] = []                 # SAN moves in play order
    turn: Optional[str] = None            # "white" | "black" (to move)
    white_clock: Optional[int] = None     # seconds remaining (if known)
    black_clock: Optional[int] = None
    finished: bool = False
    status: Optional[str] = None          # Lichess status, e.g. "started", "mate"
    winner: Optional[str] = None          # "white" | "black" when finished
    message: Optional[str] = None         # human note when unavailable


# ---------------------------------------------------------------------------
# Live match tracker (CS2 / Dota) — roadmap §3 spectator, generalized
# ---------------------------------------------------------------------------
#
# FaceIt + OpenDota don't expose a move-by-move stream like Lichess, so the
# spectator analog for those titles is a compact tracker for the player's
# current / most-recent match: headline result, status, and a few stat rows.


class MatchStat(BaseModel):
    label: str
    value: str


class MatchTrackerResponse(BaseModel):
    available: bool
    headline: Optional[str] = None        # e.g. "Victory" / "16 – 14"
    subtitle: Optional[str] = None        # e.g. "Radiant · 9/3/4 · 32:15"
    status: Optional[str] = None          # "Live" | "Final"
    result: Optional[str] = None          # "won" | "lost" | None
    url: Optional[str] = None
    stats: list[MatchStat] = []
    message: Optional[str] = None         # human note when unavailable
