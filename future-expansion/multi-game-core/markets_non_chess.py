# Snapshot from apps/api/src/moneymatch_api/services/markets.py at tag pre-chess-only. Not imported or tested.

KIND_WIN_NEXT = "win_next"
KIND_STAT_RACE = "stat_race"

MARKETS_NON_CHESS = (
    # Dota 2 — next-match win + stat duels.
    MarketDef(
        game=GAME_DOTA2_OPENDOTA,
        key="win_next",
        label="Win your next match",
        kind=KIND_WIN_NEXT,
    ),
    MarketDef(
        game=GAME_DOTA2_OPENDOTA,
        key="kda_ratio",
        label="KDA ratio",
        kind=KIND_STAT_RACE,
        metric="dota2_kda_ratio",
    ),
    MarketDef(
        game=GAME_DOTA2_OPENDOTA,
        key="gpm",
        label="GPM",
        kind=KIND_STAT_RACE,
        metric="dota2_gpm",
    ),
    # PUBG — next-match win + stat duels.
    MarketDef(
        game=GAME_PUBG_STEAM,
        key="win_next",
        label="Win your next match",
        kind=KIND_WIN_NEXT,
    ),
    MarketDef(
        game=GAME_PUBG_STEAM,
        key="kills",
        label="Kills",
        kind=KIND_STAT_RACE,
        metric="pubg_kills",
    ),
    MarketDef(
        game=GAME_PUBG_STEAM,
        key="damage",
        label="Damage",
        kind=KIND_STAT_RACE,
        metric="pubg_damage",
    ),
    MarketDef(
        game=GAME_PUBG_STEAM,
        key="headshot_pct",
        label="Headshot %",
        kind=KIND_STAT_RACE,
        metric="pubg_headshot_pct",
    ),
)
