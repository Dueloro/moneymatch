# Snapshot from apps/api/src/moneymatch_api/constants.py at tag pre-chess-only. Not imported or tested.

GAME_DOTA2_OPENDOTA = "dota2.opendota"
GAME_PUBG_STEAM = "pubg.steam"

GAME_DISPLAY_NAMES_NON_CHESS = {
    GAME_DOTA2_OPENDOTA: "Dota 2 — OpenDota",
    GAME_PUBG_STEAM: "PUBG: Battlegrounds",
}

# Entries for GAME_RATE_METRICS and POOL_METRICS (identical).
GAME_RATE_METRICS_NON_CHESS = {
    GAME_DOTA2_OPENDOTA: ("dota2_kda_ratio", "dota2_gpm"),
    GAME_PUBG_STEAM: ("pubg_kills", "pubg_damage", "pubg_headshot_pct"),
}
POOL_METRICS_NON_CHESS = GAME_RATE_METRICS_NON_CHESS

GAME_HISTORY_FLOOR_NON_CHESS = {
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

METRIC_BAR_INCREMENT_NON_CHESS = {
    "dota2_kda_ratio": 0.1,
    "dota2_gpm": 10.0,
    "pubg_kills": 1.0,
    "pubg_damage": 10.0,
    "pubg_headshot_pct": 1.0,
}

METRIC_LABELS_NON_CHESS = {
    "dota2_kda_ratio": "KDA ratio",
    "dota2_gpm": "GPM",
    "pubg_kills": "Kills",
    "pubg_damage": "Damage",
    "pubg_headshot_pct": "Headshot %",
}
