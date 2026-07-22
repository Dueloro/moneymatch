"""Domain constants shared across the API.

Game ids are the canonical `<game>.<host>` identifiers used everywhere
(linked_accounts.game, markets, adapter registry keys).
"""

from __future__ import annotations

GAME_CHESS_LICHESS = "chess.lichess"
GAME_CS2_FACEIT = "cs2.faceit"
GAME_DOTA2_OPENDOTA = "dota2.opendota"

REGISTERED_GAMES: tuple[str, ...] = (
    GAME_CHESS_LICHESS,
    GAME_CS2_FACEIT,
    GAME_DOTA2_OPENDOTA,
)

# Human labels for the Profile "Linked games" rows (design PDF p.12).
GAME_DISPLAY_NAMES: dict[str, str] = {
    GAME_CHESS_LICHESS: "Chess — Lichess",
    GAME_CS2_FACEIT: "CS2 — FACEIT",
    GAME_DOTA2_OPENDOTA: "Dota 2 — OpenDota",
}


def game_display_name(game_id: str) -> str:
    return GAME_DISPLAY_NAMES.get(game_id, game_id)


# Feature-flag keys seeded in the first migration and readable/writable by admin.
FLAG_QUEUE_PAUSED = "queue_paused"
FLAG_SETTLEMENT_PAUSED = "settlement_paused"
FLAG_GEO_CONFIG = "geo_config"

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
GAME_RATE_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CHESS_LICHESS: (),
    GAME_CS2_FACEIT: ("cs2_kd_ratio", "cs2_adr", "cs2_headshot_pct"),
    GAME_DOTA2_OPENDOTA: ("dota2_kda_ratio", "dota2_gpm"),
}

# EWMA recency weighting expressed as a half-life in matches.
METRIC_EWMA_HALF_LIFE = 10

# Below this per-metric sample size the metric is **provisional** — no stat
# duels / pool entries on it (challenge-engine proposal §3/§6).
METRIC_PROVISIONAL_MIN_N = 10

# Per-game finished-history floor. An account below it gets H2H `win` markets
# only (no stat duels), regardless of any single metric's n.
GAME_HISTORY_FLOOR: dict[str, int] = {
    GAME_CHESS_LICHESS: 20,  # rated games
    GAME_CS2_FACEIT: 25,  # matches
    GAME_DOTA2_OPENDOTA: 25,  # matches
}


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
POOL_GAMES: tuple[str, ...] = (GAME_CS2_FACEIT,)
TOURNAMENT_GAMES: tuple[str, ...] = (GAME_CS2_FACEIT,)

# Metrics offered for pools/tournaments per game (rate-based allowlist only).
POOL_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CS2_FACEIT: ("cs2_kd_ratio", "cs2_adr", "cs2_headshot_pct"),
}
TOURNAMENT_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CS2_FACEIT: ("cs2_kd_ratio", "cs2_adr", "cs2_headshot_pct"),
}

# Personal-bar difficulty multipliers: bar = round(μ + k·σ). Implied clear rate
# is 1 − Φ(k) (≈31% / 16% / 4%) — disclosed difficulty, never an odds line.
POOL_DIFFICULTY_K: dict[str, float] = {"easy": 0.5, "medium": 1.0, "hard": 1.75}

# Rounding increment for a personal/room bar, per metric (bars are quoted to a
# clean step so two players' bars are comparable and reproducible).
METRIC_BAR_INCREMENT: dict[str, float] = {
    "cs2_kd_ratio": 0.05,
    "cs2_adr": 1.0,
    "cs2_headshot_pct": 1.0,
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
    "cs2_kd_ratio": "K/D ratio",
    "cs2_adr": "ADR",
    "cs2_headshot_pct": "Headshot %",
    "dota2_kda_ratio": "KDA ratio",
    "dota2_gpm": "GPM",
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
