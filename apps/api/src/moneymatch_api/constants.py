"""Domain constants shared across the API."""

from __future__ import annotations

GAME_CHESS_LICHESS = "chess.lichess"

REGISTERED_GAMES: tuple[str, ...] = (GAME_CHESS_LICHESS,)

GAME_DISPLAY_NAMES: dict[str, str] = {
    GAME_CHESS_LICHESS: "Chess — Lichess",
}


def game_display_name(game_id: str) -> str:
    return GAME_DISPLAY_NAMES.get(game_id, game_id)


FLAG_QUEUE_PAUSED = "queue_paused"
FLAG_SETTLEMENT_PAUSED = "settlement_paused"
FLAG_GEO_CONFIG = "geo_config"

# The live list lives in the `geo_config` flag so it is admin-editable without a deploy;
# this is the **boot-time floor** for a production deploy, checked once at startup.
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

FLAG_WORKER_HEARTBEAT = "worker_heartbeat"
WORKER_HEARTBEAT_STALE_SECONDS = 120  # /health and reconciliation redden past this

FLAG_NIGHTLY_LAST_RUN = "nightly_last_run"
NIGHTLY_INTERVAL_SECONDS = 24 * 3600


def game_flag_key(game_id: str) -> str:
    return f"game:{game_id}"


GAME_RATE_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CHESS_LICHESS: ("chess_moves",),
}

METRIC_EWMA_HALF_LIFE = 10  # EWMA recency half-life, in matches

STAT_BASELINE_MIN_N = 1  # graded matches needed to quote a bar


# Server-defined entry presets (no arbitrary client stakes — the client sends a preset
# choice; the server owns the cents). 500 / 1,000 / 2,500 points.
ENTRY_PRESETS_CENTS: tuple[int, ...] = (500, 1_000, 2_500)

QUEUE_TICKET_TTL_SECONDS = 600  # a waiting ticket expires after 10 min

MATCH_CONFIRM_TTL_SECONDS = 24 * 3600  # unconfirmed match is canceled, no rake

MATCH_SETTLE_WINDOW_SECONDS = (
    24 * 3600
)  # an ACTIVE match's qualifying game must land inside

FORMATION_WIDEN_AFTER_SECONDS = (
    300  # past this wait a ticket may form a smaller room/field
)

# Elo pairing band (rating points): starts at BASE, widens per second waited, capped.
CHESS_BASE_BAND = 100
CHESS_BAND_GROWTH_PER_SEC = 12
CHESS_MAX_BAND = 800

# The clock each brokered Lichess game is created with: (limit, increment) seconds.
CHESS_CLOCKS: dict[str, tuple[int, int]] = {
    "bullet": (60, 0),
    "blitz": (300, 0),
    "rapid": (600, 0),
    "classical": (1800, 0),
}

REPAIR_COOLDOWN_SECONDS = (
    24 * 3600
)  # accounts that just played can't be re-paired inside this

GRADING_ENGINE_VERSION = (
    "h2h-1"  # stamped on settlements; bump when pairing/grading changes
)

# A host outage extends `window_ends_at` up to here; past it the match is CANCELED +
# refunded.
MATCH_MAX_LIFETIME_SECONDS = MATCH_SETTLE_WINDOW_SECONDS + 24 * 3600

WORKER_POLL_INTERVAL_SECONDS = 15  # settlement worker cadence


POOL_GAMES: tuple[str, ...] = REGISTERED_GAMES
TOURNAMENT_GAMES: tuple[str, ...] = REGISTERED_GAMES

POOL_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CHESS_LICHESS: ("chess_moves",),
}
TOURNAMENT_METRICS: dict[str, tuple[str, ...]] = {
    GAME_CHESS_LICHESS: ("chess_win_streak", "chess_wins", "chess_fastest_win"),
}

# z-scores; implied clear rate is 1 - Phi(k): ~35% / 20% / 10%.
POOL_DIFFICULTY_K: dict[str, float] = {"easy": 0.385, "medium": 0.842, "hard": 1.282}

METRIC_POSITIVE_SUPPORT: frozenset[str] = frozenset({"chess_moves"})

METRIC_REQUIRES_WIN: frozenset[str] = frozenset({"chess_moves"})


def requires_win(metric: str) -> bool:
    """True when only won matches produce a value for this metric."""
    return metric in METRIC_REQUIRES_WIN


METRIC_FLOOR: dict[str, float] = {"chess_moves": 2.0}


def positive_support(metric: str) -> bool:
    """True when the metric cannot be zero or negative (use a lognormal bar)."""
    return metric in METRIC_POSITIVE_SUPPORT


def metric_floor(metric: str) -> float:
    """The hard minimum a quoted bar may never fall below."""
    return METRIC_FLOOR.get(metric, 0.0)


METRIC_LOWER_IS_BETTER: frozenset[str] = frozenset({"chess_moves"})


def lower_is_better(metric: str) -> bool:
    """True when a smaller value wins (fewest moves), false for a rate stat."""
    return metric in METRIC_LOWER_IS_BETTER


RATED_ONLY_GAMES: frozenset[str] = frozenset({GAME_CHESS_LICHESS})


def rated_only_game(game: str) -> bool:
    """True when this game must be settled from rated matches only."""
    return game in RATED_ONLY_GAMES


# Rounding increment for a personal/room bar, per metric (bars are quoted to a clean
# step so two players' bars are comparable and reproducible).
METRIC_BAR_INCREMENT: dict[str, float] = {
    "chess_accuracy": 1.0,
    "chess_moves": 1.0,
}

POOL_ROOM_SIZE = 4
POOL_MIN_ROOM = 3
POOL_BAR_SPREAD_CAP_SIGMA = 1.5  # personal-bar spread cap across a room, x pooled sigma
POOL_WINDOW_SECONDS = 24 * 3600
TOURNAMENT_FIELD_SIZE = 10
TOURNAMENT_MIN_FIELD = 6
TOURNAMENT_MIN_RANKED = 4
TOURNAMENT_PRIZE_SPLIT: tuple[int, ...] = (50, 30, 20)  # relative weights, 1st-3rd
TOURNAMENT_DISPERSION_CAP = 1.0  # max(mu) - min(mu) <= cap * pooled sigma
TOURNAMENT_WINDOW_SECONDS = 48 * 3600
TOURNAMENT_STANDINGS_REFRESH_SECONDS = 10 * 60
LIVE_SNAPSHOT_REFRESH_SECONDS = 30
# An in-flight board older than this is withheld (the stage shows only the link).
LIVE_SNAPSHOT_STALE_SECONDS = 90

# Engine-version stamps for pool/tournament settlements (dispute replay).
POOL_ENGINE_VERSION = "pool-1"
TOURNAMENT_ENGINE_VERSION = "tourney-1"

SANDBAG_RECENT_N = 10
SANDBAG_Z_THRESHOLD = (
    -1.5
)  # recent-N mean this many z below lifetime mean => flag + block

WIN_STREAK_THRESHOLD = (
    8  # H2H win run that raises an informational risk flag (no block)
)

METRIC_LABELS: dict[str, str] = {
    "chess_accuracy": "Accuracy",
    "chess_moves": "Moves to win",
    "chess_win_streak": "Longest win streak",
    "chess_wins": "Total wins",
    "chess_fastest_win": "Fastest win",
}


def metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric)


MAX_FRIENDS = 500
MAX_PENDING_OUTBOUND = 20

PRESENCE_WINDOW_SECONDS = 5 * 60

CHALLENGE_TTL_SECONDS = 24 * 3600

# Anti-collusion pair caps on **rake-bearing** contests between the same two accounts
# (friends included).
PAIR_RAKE_CONTESTS_PER_DAY = 3
PAIR_RAKE_CONTESTS_PER_WEEK = 10

# Leaderboard: rank real users by ROI over a rolling window; a minimum number of settled
# rake-bearing contests qualifies you.
LEADERBOARD_WINDOW_DAYS = 30
LEADERBOARD_MIN_CONTESTS = 3
