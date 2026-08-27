"""Domain constants shared across the API.

Game ids are the canonical `<game>.<host>` identifiers used everywhere
(linked_accounts.game, markets, adapter registry keys).
"""

from __future__ import annotations

GAME_CHESS_LICHESS = "chess.lichess"
GAME_CS2_STEAM = "cs2.steam"
GAME_DOTA2_OPENDOTA = "dota2.opendota"
GAME_PUBG_STEAM = "pubg.steam"

# Games with a verification adapter + skill model — the fully playable set. All
# matchmaking / skill / linking code keys off this tuple, so a game only belongs
# here once its adapter and metrics exist.
REGISTERED_GAMES: tuple[str, ...] = (
    GAME_CHESS_LICHESS,
    GAME_CS2_STEAM,
    GAME_DOTA2_OPENDOTA,
    GAME_PUBG_STEAM,
)

# Announced games with no adapter yet: selectable in the catalog but not linkable
# or playable — the UI shows "coming soon". Empty now that PUBG is live; keep the
# seam so the next announced-but-unbuilt game can slot in here.
COMING_SOON_GAMES: tuple[str, ...] = ()

# The full selectable catalog surfaced by /links and the games bar.
CATALOG_GAMES: tuple[str, ...] = REGISTERED_GAMES + COMING_SOON_GAMES

# Human labels for the Profile "Games" rows (design PDF p.12).
GAME_DISPLAY_NAMES: dict[str, str] = {
    GAME_CS2_STEAM: "Counter-Strike 2 (Steam)",
    GAME_CHESS_LICHESS: "Chess — Lichess",
    GAME_DOTA2_OPENDOTA: "Dota 2 — OpenDota",
    GAME_PUBG_STEAM: "PUBG: Battlegrounds",
}


def game_display_name(game_id: str) -> str:
    return GAME_DISPLAY_NAMES.get(game_id, game_id)


def is_coming_soon(game_id: str) -> bool:
    return game_id in COMING_SOON_GAMES


# Demo-login bypass (see routers/demo.py + config.demo_login_enabled). One shared
# demo user, provisioned + onboarded on first login. The signing key is not a
# real secret: a demo token only ever grants this demo user, and is only minted
# or accepted when demo_login_enabled is on. Play-money demos only.
DEMO_AUTH_ID = "demo-user"
DEMO_EMAIL = "demo@dueloro.com"
DEMO_USERNAME = "demo"
DEMO_RESIDENCE_STATE = "MA"
DEMO_JWT_SECRET = "moneymatch-demo-login-signing-key-not-a-secret"  # noqa: S105 (see above)


# Feature-flag keys seeded in the first migration and readable/writable by admin.
FLAG_QUEUE_PAUSED = "queue_paused"
FLAG_SETTLEMENT_PAUSED = "settlement_paused"
FLAG_GEO_CONFIG = "geo_config"

# The 14 excluded ("Any Chance") states seeded by migration 0001. The live list
# lives in the `geo_config` flag so it is admin-editable without a deploy; this
# is the **boot-time floor** for a production deploy, checked once at startup.
#
# The point is that a fresh or half-restored database cannot quietly come up
# with a smaller fence than the one the product was designed around. A deploy
# that would do so fails loudly, which is cheap; booting with a hole in the
# geo-fence is not.
#
# Note the tension this creates, deliberately: an admin can still *add* states
# without a deploy, but cannot drop below this floor in prod without a code
# change. If a state's legal position changes, that is a code change plus a
# deploy — see OPEN_QUESTIONS.md Q7.
GEO_REQUIRED_EXCLUDED_STATES: frozenset[str] = frozenset(
    {
        "AZ",
        "AR",
        "CT",
        "DE",
        "FL",
        "IN",
        "LA",
        "MD",
        "MN",
        "MT",
        "SC",
        "SD",
        "TN",
        "WY",
    }
)

# The settlement worker writes its liveness here each cycle (payload `{"ts": iso}`);
# /health and the admin reconciliation view redden when it goes stale (09-phase-6 ·
# deliverable 4 · worker heartbeat).
FLAG_WORKER_HEARTBEAT = "worker_heartbeat"
WORKER_HEARTBEAT_STALE_SECONDS = 120

# The worker runs a heavier nightly pass (metric-model refresh + derived risk
# detectors) at most once per interval; the last-run timestamp lives in this flag
# (payload `{"ts": iso}`), same mechanism as the heartbeat (backlog · Phase B).
FLAG_NIGHTLY_LAST_RUN = "nightly_last_run"
NIGHTLY_INTERVAL_SECONDS = 24 * 3600


# Per-game enable flags (game:<id>).
def game_flag_key(game_id: str) -> str:
    return f"game:{game_id}"


# --------------------------------------------------------------------------- #
# Metric-model config (05-phase-2 · deliverable 6).
# "Floors live in config, not code" — tune these here, never inline in the
# bootstrap logic. Metrics are the typed, rate-based allowlist only (never raw
# totals, never anything outside the player's control — 01-architecture §2).
# --------------------------------------------------------------------------- #

# Rate metrics we build EWMA skill models for, per game. Chess settles on `win`
# only, so it models no per-metric skill here.
# Metrics we build EWMA skill models for from host history (bootstrap polls
# these on link). Chess models `chess_moves`, read straight off each game record
# Lichess already returns. `chess_accuracy` is retained only because demo
# fixtures seed it; it has no live source and is no longer offered for pools.
# --------------------------------------------------------------------------- #
# CS2 over Steam.
#
# Everything below comes from the Game Coordinator scoreboard, which a share
# code resolves to. Deliberately absent: `cs2_adr`. ADR needs a parsed demo,
# and a market that cannot be graded is worse than three that can.
#
# All three are rates where a bigger number is better, so a harder tier asks
# for more. The opposite of chess `moves`.
# --------------------------------------------------------------------------- #
CS2_STEAM_METRICS: tuple[str, ...] = (
    "cs2_kd_ratio",
    "cs2_headshot_pct",
    "cs2_kills",
)

# A real Premier/Competitive match runs at least 16 rounds; 13-3 is the
# shortest legitimate scoreline. Wingman is first to 9. Below the floor the
# match was surrendered or abandoned, and grading it would let a three-round
# forfeit stand in for a real result.
CS2_MIN_ROUNDS_STANDARD = 16
CS2_MIN_ROUNDS_WINGMAN = 9
#: Wingman is 2v2, so the roster size is how the mode is told apart.
CS2_WINGMAN_MAX_PLAYERS = 4


def cs2_min_rounds(player_count: int) -> int:
    """The round floor for the mode implied by the roster size."""
    if player_count and player_count <= CS2_WINGMAN_MAX_PLAYERS:
        return CS2_MIN_ROUNDS_WINGMAN
    return CS2_MIN_ROUNDS_STANDARD


GAME_RATE_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CS2_STEAM: CS2_STEAM_METRICS,
    GAME_CHESS_LICHESS: ("chess_moves",),
    GAME_DOTA2_OPENDOTA: ("dota2_kda_ratio", "dota2_gpm"),
    GAME_PUBG_STEAM: ("pubg_kills", "pubg_damage", "pubg_headshot_pct"),
}

# EWMA recency weighting expressed as a half-life in matches.
METRIC_EWMA_HALF_LIFE = 10

# Below this per-metric sample size a Head-to-Head **stat duel** is provisional
# (challenge-engine proposal §3/§6).
METRIC_PROVISIONAL_MIN_N = 10

# Solo pools / tournaments no longer gate on a "play more matches to unlock"
# sample floor — they're available as soon as there's a baseline to quote a bar
# from, i.e. at least one graded match on the stat. (Zero samples has no μ/σ, so
# a stat you've never produced simply isn't offered — that's math, not a rule.)
STAT_BASELINE_MIN_N = 1

# Per-game finished-history floor. An account below it gets H2H `win` markets
# only (no stat duels), regardless of any single metric's n.
GAME_HISTORY_FLOOR: dict[str, int] = {
    # A Steam user starts with no history in our system; the prior comes from
    # their Steam lifetime stats instead, so nothing is gated on match count.
    GAME_CS2_STEAM: 0,
    GAME_CHESS_LICHESS: 20,  # rated games
    GAME_DOTA2_OPENDOTA: 25,  # matches
    GAME_PUBG_STEAM: 20,  # matches
}

# PUBG per-poll match fan-out cap. Bootstrap needs ≥ METRIC_PROVISIONAL_MIN_N
# graded samples to lift a stat duel out of "provisional"; 15 clears 10 even
# after custom/event matches are filtered out. Settlement stays cheap via the
# poll's newest-first early-exit + the finished-match cache.
PUBG_MATCH_FANOUT = 15

# Official PUBG modes eligible to settle money. Everything else — custom games,
# arcade, war/zombie, event, training — is excluded so only standard
# battle-royale play grades a duel.
PUBG_OFFICIAL_GAME_MODES: frozenset[str] = frozenset(
    {"solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"}
)
PUBG_OFFICIAL_MATCH_TYPES: frozenset[str] = frozenset({"official", "competitive"})


# --------------------------------------------------------------------------- #
# Head-to-head play config (06-phase-3). All timing/entry knobs live here, not
# inline in the matchmaking / lifecycle / worker code.
# --------------------------------------------------------------------------- #

# Server-defined entry presets (no arbitrary client stakes — the client sends a
# preset choice; the server owns the cents). $5 / $10 / $25.
ENTRY_PRESETS_CENTS: tuple[int, ...] = (500, 1_000, 2_500)

# A waiting queue ticket ages out after this (worker expires it; no escrow was
# ever taken while waiting). Phase 3 deliverable 2 · "Ticket TTL (10 min)".
QUEUE_TICKET_TTL_SECONDS = 600

# A PENDING match (paired, awaiting both confirms) expires here → refund the
# confirmer, no rake (architecture §2 · "expiry (window_ends_at, 24 h)").
MATCH_CONFIRM_TTL_SECONDS = 24 * 3600

# Once ACTIVE, the settlement window: each player's qualifying match must land
# inside it. Host outage extends it, never past this ceiling from `matched_at`.
MATCH_SETTLE_WINDOW_SECONDS = 24 * 3600

# One-sided stat-duel forfeit: the player who produced a qualifying match wins,
# but only after the full window PLUS this disclosed grace period (printed on the
# slip pre-entry — Phase 3 deliverable 4 · forfeit rule).
FORFEIT_GRACE_SECONDS = 2 * 3600

# --- Duel-forecast pairing (launch-plan §4.5(d)) --------------------------- #
# Stat-duel eligibility band half-width `w`: pair only if the forecast
# P(a beats b) ∈ [0.5 − w, 0.5 + w]. Widens with wait time (the ladder). Each
# entry is (max_age_seconds, w); the last stage is the widest offered before we
# fall back to keep-waiting / cancel-refund.
PAIRING_WIDENING_LADDER: tuple[tuple[int, float], ...] = (
    (30, 0.05),
    (120, 0.10),
    (300, 0.15),
)

# Chess uses the Elo rating band instead of the stat forecast (Elo already *is*
# the forecast — PoC constants). Band starts at 100, widens 12/s, capped at 800.
CHESS_BASE_BAND = 100
CHESS_BAND_GROWTH_PER_SEC = 12
CHESS_MAX_BAND = 800

# Composite-selection weights among eligible candidates (lower score = better):
# 0.60·|μa−μb|/σ_pooled + 0.30·rating distance + 0.10·|σa−σb|/σ_pooled.
SELECT_W_MEAN_GAP = 0.60
SELECT_W_RATING = 0.30
SELECT_W_VARIANCE = 0.10

# Two accounts that just played can't be re-paired within this window
# (anti-collusion `can_pair` seam — Phase 3 deliverable 2).
REPAIR_COOLDOWN_SECONDS = 24 * 3600

# Stamped on every settlement (`matches.engine_version`) so a dispute knows
# exactly which matchmaking/grading rules produced the result (01-architecture §2).
# Bump when pairing or grading logic changes.
GRADING_ENGINE_VERSION = "h2h-1"

# Absolute ceiling on a match's life from `matched_at`: the settlement window
# (24 h) plus the outage ceiling (24 h). A host outage extends `window_ends_at`
# up to here; past it the match is CANCELED + refunded (failure matrix,
# 01-architecture §3.4 · "24 h hard ceiling").
MATCH_MAX_LIFETIME_SECONDS = MATCH_SETTLE_WINDOW_SECONDS + 24 * 3600

# Clock-skew tolerance when deciding a host match landed "after" `matched_at`.
GRADE_MATCH_SKEW_MS = 60_000

# The settlement worker's poll cadence (01-architecture §3.3 · "every ~15 s").
WORKER_POLL_INTERVAL_SECONDS = 15


# --------------------------------------------------------------------------- #
# Solo pools & tournaments config (07-phase-4). CS2 only at MVP — the one
# adapter with rich server-fetchable telemetry. All fairness constants live
# here, never inline in the engines ("all constants in config").
# --------------------------------------------------------------------------- #

# Which games offer pools/tournaments (config, not code — the engine is
# game-agnostic; chess/dota wait for richer/validated telemetry).
# Solo pools & tournaments run on every playable game's rate metrics.
POOL_GAMES: tuple[str, ...] = REGISTERED_GAMES
TOURNAMENT_GAMES: tuple[str, ...] = REGISTERED_GAMES

# Metrics offered for pools/tournaments per game (rate-based allowlist only).
POOL_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CS2_STEAM: CS2_STEAM_METRICS,
    GAME_CHESS_LICHESS: ("chess_moves",),
    GAME_DOTA2_OPENDOTA: ("dota2_kda_ratio", "dota2_gpm"),
    GAME_PUBG_STEAM: ("pubg_kills", "pubg_damage", "pubg_headshot_pct"),
}
# Tournaments are no longer just "pools with a bigger field". Chess runs the
# three aggregate contests the Lichess record actually supports (see
# `services/aggregate_metrics.py`); every other game still scores its rate
# metrics as a first-N mean.
TOURNAMENT_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CS2_STEAM: CS2_STEAM_METRICS,
    **POOL_METRICS,
    GAME_CHESS_LICHESS: ("chess_win_streak", "chess_wins", "chess_fastest_win"),
}

# Personal-bar difficulty multipliers, as z-scores. Implied clear rate is
# 1 − Φ(k): disclosed difficulty, never an odds line.
#
#   easy   k = 0.385  ->  35%, about 1 game in 3
#   medium k = 0.842  ->  20%, about 1 in 5
#   hard   k = 1.282  ->  10%, about 1 in 10
#
# These were 0.5 / 1.0 / 1.75 (31% / 16% / 4%). A 4% tier is a bar you miss
# nineteen times out of twenty, which reads as broken rather than hard, and it
# sits so far into the tail that it is exactly where a fitted distribution is
# least trustworthy. Ending on round odds also makes the card self-explaining.
POOL_DIFFICULTY_K: dict[str, float] = {"easy": 0.385, "medium": 0.842, "hard": 1.282}

# Metrics that measure a strictly positive quantity with a long right tail:
# moves in a game, damage, duration. Their bars are placed on a lognormal
# instead of a normal (see `fairness.personal_bar`), because `μ − k·σ` on a
# normal can leave the scale entirely once σ approaches μ.
METRIC_POSITIVE_SUPPORT: frozenset[str] = frozenset({"chess_moves"})

# Metrics that only count when you WON the match.
#
# `chess_moves` without this is trivially exploitable in the wrong direction:
# the bar is "come in at or under N moves", and resigning on move one scores 1.
# A bot could clear every hard pool by instantly resigning, which is both the
# cheapest possible action and a guaranteed win. Requiring the win makes the
# only way to score the thing the card actually claims: a fast victory.
#
# The adapter enforces it by not emitting the metric at all for a game you did
# not win, so a lost game contributes nothing to your baseline either: the
# average becomes "moves I take to win", which is what a bar quoted in moves is
# supposed to mean.
METRIC_REQUIRES_WIN: frozenset[str] = frozenset({"chess_moves"})


def requires_win(metric: str) -> bool:
    """True when only won matches produce a value for this metric."""
    return metric in METRIC_REQUIRES_WIN


# The smallest value the metric can physically take. A backstop, not a tuning
# knob: with a lognormal the bar should never approach it. Two full moves is
# Fool's Mate, the shortest possible chess game.
METRIC_FLOOR: dict[str, float] = {"chess_moves": 2.0}


def positive_support(metric: str) -> bool:
    """True when the metric cannot be zero or negative (use a lognormal bar)."""
    return metric in METRIC_POSITIVE_SUPPORT


def metric_floor(metric: str) -> float:
    """The hard minimum a quoted bar may never fall below."""
    return METRIC_FLOOR.get(metric, 0.0)


# Metrics where a SMALLER number is the better result. For these the bar is
# μ − k·σ and you clear by coming in at or under it, so a harder pool asks for
# fewer moves rather than more.
#
# The maths stays symmetric: at bar = μ − k·σ the implied clear rate is
# Φ((bar−μ)/σ) = Φ(−k) = 1 − Φ(k), exactly the rate a higher-is-better metric
# gets at the same k. Difficulty means the same thing in both directions.
METRIC_LOWER_IS_BETTER: frozenset[str] = frozenset({"chess_moves"})


def lower_is_better(metric: str) -> bool:
    """True when a smaller value wins (fewest moves), false for a rate stat."""
    return metric in METRIC_LOWER_IS_BETTER


# Games settled from rated matches only. Chess needs it — a casual or
# vs-computer game is trivial to farm, and a brokered chess duel is itself
# casual — while other hosts count casual games as they always have.
RATED_ONLY_GAMES: frozenset[str] = frozenset({GAME_CHESS_LICHESS})


def rated_only_game(game: str) -> bool:
    """True when this game must be settled from rated matches only."""
    return game in RATED_ONLY_GAMES


# Rounding increment for a personal/room bar, per metric (bars are quoted to a
# clean step so two players' bars are comparable and reproducible).
METRIC_BAR_INCREMENT: dict[str, float] = {
    "chess_accuracy": 1.0,
    "chess_moves": 1.0,
    "cs2_kd_ratio": 0.05,
    # `cs2_adr` was removed here when migration 0024 retired the FACEIT adapter.
    # ADR needs a parsed demo file, which the Game Coordinator scoreboard does
    # not carry, so there is no market to quote an increment for. An increment
    # for a market that cannot be graded is a trap for whoever adds the next one.
    "cs2_headshot_pct": 1.0,
    "cs2_kills": 1.0,
    "dota2_kda_ratio": 0.1,
    "dota2_gpm": 10.0,
    "pubg_kills": 1.0,
    "pubg_damage": 10.0,
    "pubg_headshot_pct": 1.0,
}

# Room formation. A full room is `POOL_ROOM_SIZE`; at ladder end we form down to
# `POOL_MIN_ROOM`. The composition predicate keeps every member's implied clear
# probability vs. the room bar inside [p_target/2, min(2·p_target, 0.5)].
POOL_ROOM_SIZE = 4
POOL_MIN_ROOM = 3
# Personal-bar spread cap across a room, as a multiple of the pooled σ.
POOL_BAR_SPREAD_CAP_SIGMA = 1.5
# The pool settlement window: your first qualifying match must land inside it.
POOL_WINDOW_SECONDS = 24 * 3600
# Tournament field. Formed under a μ-dispersion cap; scored on the mean of the
# first-N qualifying matches; top places split per `TOURNAMENT_PRIZE_SPLIT`.
TOURNAMENT_FIELD_SIZE = 10
TOURNAMENT_MIN_FIELD = 6
TOURNAMENT_MIN_RANKED = 4
TOURNAMENT_SCORE_N = 3
TOURNAMENT_PRIZE_SPLIT: tuple[int, ...] = (50, 30, 20)  # relative weights
# max(μ) − min(μ) ≤ dispersion_cap · σ_pooled (start tight, tune with data).
TOURNAMENT_DISPERSION_CAP = 1.0
TOURNAMENT_WINDOW_SECONDS = 48 * 3600
# Live standings refresh cadence during the window (cheap, cached).
TOURNAMENT_STANDINGS_REFRESH_SECONDS = 10 * 60
# Live under-the-card refresh cadence for in-flight pools & H2H matches. Faster
# than standings — a chess board wants to feel live — but still host-cached so
# the Activity request path never makes a host call.
LIVE_SNAPSHOT_REFRESH_SECONDS = 30

# Engine-version stamps for pool/tournament settlements (dispute replay).
POOL_ENGINE_VERSION = "pool-1"
TOURNAMENT_ENGINE_VERSION = "tourney-1"

# Sandbagging detector v1: flag + block when the recent-N mean sits z-below the
# lifetime mean (tanking a baseline is the attack the personal bar invites).
SANDBAG_RECENT_N = 10
SANDBAG_Z_THRESHOLD = -1.5

# Derived risk detector (nightly): an unbroken run of this many settled H2H wins
# writes an informational `win_streak` risk flag for admin review. Unlike a
# sandbagging flag it does NOT block wagers — it only surfaces in the risk queue.
WIN_STREAK_THRESHOLD = 8

# Human labels for rate metrics (pool/tournament market rows + standings).
METRIC_LABELS: dict[str, str] = {
    "chess_accuracy": "Accuracy",
    "chess_moves": "Moves to win",
    "chess_win_streak": "Longest win streak",
    "chess_wins": "Total wins",
    "chess_fastest_win": "Fastest win",
    "cs2_kd_ratio": "K/D ratio",
    # `cs2_adr` intentionally absent — retired with the FACEIT adapter (migration
    # 0024); ADR needs a parsed demo the Game Coordinator scoreboard lacks.
    "cs2_headshot_pct": "Headshot %",
    "cs2_kills": "Kills",
    "dota2_kda_ratio": "KDA ratio",
    "dota2_gpm": "GPM",
    "pubg_kills": "Kills",
    "pubg_damage": "Damage",
    "pubg_headshot_pct": "Headshot %",
}


def metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric)


# --------------------------------------------------------------------------- #
# Social & retention config (08-phase-5). Caps and windows live here, never
# inline in the friends/challenge services.
# --------------------------------------------------------------------------- #

# Friendship caps (08-phase-5 · deliverable 2).
MAX_FRIENDS = 500
MAX_PENDING_OUTBOUND = 20

# Presence-lite: "active" (green dot) if the heartbeat landed within this window.
PRESENCE_WINDOW_SECONDS = 5 * 60

# Direct challenge / invite link expiry (08-phase-5 · deliverable 3).
CHALLENGE_TTL_SECONDS = 24 * 3600

# Anti-collusion pair caps on **rake-bearing** contests between the same two
# accounts (friends included). Past the cap a challenge becomes a zero-rake
# friendly instead of being blocked (08-phase-5 · collusion posture for friends).
PAIR_RAKE_CONTESTS_PER_DAY = 3
PAIR_RAKE_CONTESTS_PER_WEEK = 10

# Leaderboard: rank real users by ROI over a rolling window; a minimum number of
# settled rake-bearing contests qualifies you (08-phase-5 · deliverable 5).
LEADERBOARD_WINDOW_DAYS = 30
LEADERBOARD_MIN_CONTESTS = 3
