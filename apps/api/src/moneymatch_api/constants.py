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
