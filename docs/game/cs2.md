# CS2 (FaceIt) — live API responses

Real responses captured on **2026-08-11** by calling the FaceIt Data API v4 with
the exact parameters `services/hosts/faceit.py` sends. Nothing here is
hand-written or trimmed except where marked, so what you see is what the adapter
parses.

Sample account: **`donk666`** (an active pro, so recent matches always exist).
Swap the nickname in any URL below to see your own.

Unlike Lichess, **every call needs a server-side API key**
(`Authorization: Bearer $FACEIT_API_KEY`). Without it `faceit.is_configured()`
is false and the link path raises `HostNotConfigured` rather than pretending the
player does not exist.

Four endpoints are used for the read path, and one of them runs **once per
match**, which is the main cost difference from chess.

---

## 1. Player — `GET /players?nickname={nickname}&game=cs2`

Called by `faceit.get_player()`, parsed by `CS2FaceitAdapter._to_profile()`.
Used on link, on refresh, and to resolve a nickname to the `player_id` that
every other endpoint is keyed by.

```
https://open.faceit.com/data/v4/players?nickname=donk666&game=cs2
```

```jsonc
{
  "player_id": "e5e8e2a6-d716-4493-b949-e16965f41654",  // the key for every other call
  "nickname": "donk666",
  "avatar": "https://distribution.faceit-cdn.net/images/30b3a5e8-....jpg",
  "country": "kr",
  "faceit_url": "https://www.faceit.com/{lang}/players/donk666",  // {lang} is ours to fill
  "steam_id_64": "76561198386265483",
  "verified": true,
  "activated_at": "2017-10-27T06:09:38.834Z",
  "memberships": ["premium", "esea"],
  "games": {
    "cs2": {
      "region": "EU",
      "game_player_id": "76561198386265483",
      "game_player_name": "king",
      "skill_level": 10,           // -> rank_label "Level 10"
      "faceit_elo": 4627           // -> rating
    },
    "csgo": {                      // legacy block, still present on old accounts
      "skill_level": 10,
      "faceit_elo": 5977           // a DIFFERENT number; not ours to read
    }
  },
  "infractions": { /* ... */ },
  "platforms": { /* ... */ },
  "settings": { /* ... */ }
}
```

**How it maps to `ProfileSnapshot`:**

| FaceIt field | Our field | Note |
| --- | --- | --- |
| `nickname` | `username`, `display_name` | |
| `faceit_url` | `url` | `{lang}` is replaced with `en` |
| `avatar` | `avatar_url` | |
| `games.cs2.faceit_elo` | `rating` | The Elo you would matchmake on |
| `games.cs2.skill_level` | `rank_label` | Rendered as `Level 10` |

Three things worth knowing:

**The `csgo` block is a trap.** Old accounts carry both, with different Elo
(5977 vs 4627 here). The adapter reads `games.cs2` only. If a player has a
`csgo` block and no `cs2` block, `fetch_profile` raises rather than inventing a
profile that could never settle a CS2 match.

**A 404 does not mean the player is missing.** `?game=cs2` 404s for an account
without that block, so `get_player()` retries the lookup without the filter. Of
the eight pro nicknames tried while capturing this, `s1mple` and `NiKo` 404
either way; `donk666`, `ZywOo`, `m0NESY`, `device`, `ropz` and `broky` resolve.

**No account age gate.** `activated_at` is captured but unused; chess uses
`createdAt` for `account_age_days`, CS2 leaves it null.

---

## 2. Lifetime stats — `GET /players/{player_id}/stats/cs2`

Called by `faceit.get_player_stats()`, which returns the `lifetime` block only.
Used for the overall record shown on the profile card.

```
https://open.faceit.com/data/v4/players/e5e8e2a6-.../stats/cs2
```

```jsonc
{
  "lifetime": {
    "Matches": "7199",
    "Wins": "4364",
    "Win Rate %": "61",
    "Average K/D Ratio": "1.45",     // <- the one the adapter reads
    "K/D Ratio": "10419.3",          // <- cumulative total, NOT a ratio
    "ADR": "114.15",
    "Average Headshots %": "60",
    "Current Win Streak": "1",
    "Longest Win Streak": "22",
    "Recent Results": ["1", "1", "1", "0", "1"],   // 1 = win, newest last
    // ~30 more: entry rates, flash stats, utility damage, 1v1/1v2 clutches
  }
}
```

**How it maps:**

| FaceIt field | Our field | Note |
| --- | --- | --- |
| `Matches` | `total_games` | Gates `GAME_HISTORY_FLOOR` (CS2: 25) |
| `Win Rate %` | `win_rate` | Divided by 100; defaults to 0.5 when absent |
| `Average K/D Ratio` | `kd` | |

**Every value is a string**, including the numbers. `_to_float()` exists for
exactly this, and returns `None` rather than raising on anything unparseable.

**`K/D Ratio` in this block is not a K/D ratio.** It reads `10419.3` for a
player whose actual average is `1.45`, so it is a running total of something,
not a rate. The adapter correctly reads `Average K/D Ratio`. Anyone adding a
metric here should check the value against a known player before trusting the
field name.

`draw_rate` is hardcoded to `0.0`: CS2 matchmaking does not draw.

---

## 3. Match history — `GET /players/{player_id}/history?game=cs2`

Called by `faceit.get_player_history()`, parsed by `_normalize()`. This is the
settlement and metric-modelling feed.

Exact query the adapter sends:

```
https://open.faceit.com/data/v4/players/{player_id}/history
  ?game=cs2
  &limit=20        // the adapter's default
  &from=1786455803 // epoch SECONDS, and 60s earlier than asked for (clock skew)
```

One full item, unedited apart from trimming the player lists:

```jsonc
{
  "match_id": "1-98cf6a9c-c1a0-46ca-8d85-c1103fcde074",
  "game_id": "cs2",
  "region": "EU",
  "game_mode": "5v5",
  "match_type": "",
  "max_players": 10,
  "teams_size": 5,
  "competition_id": "...",
  "competition_name": "Europe 5v5 Queue",
  "competition_type": "matchmaking",     // vs "championship" for organised play
  "organizer_id": "faceit",
  "status": "finished",                  // anything else is skipped
  "started_at": 1786455863,              // epoch SECONDS -> created_at_ms (x1000)
  "finished_at": 1786458151,
  "teams": {
    "faction1": {
      "team_id": "641bc080-6868-4cee-bb4c-044dd05f7d1c",
      "nickname": "team_donk666",
      "players": [
        { "player_id": "e5e8e2a6-...", "nickname": "donk666", "skill_level": 10 }
        // 4 more
      ]
    },
    "faction2": { "team_id": "960d9e7a-...", "players": [ /* 5 */ ] }
  },
  "results": {
    "winner": "faction1",                // a FACTION KEY, not a team_id
    "score": { "faction1": 13, "faction2": 9 }
  },
  "faceit_url": "https://www.faceit.com/{lang}/cs2/room/1-98cf6a9c-..."
}
```

**How it maps to `NormGame`:**

| FaceIt field | Our field | Note |
| --- | --- | --- |
| `match_id` | `id` | What `/matches/{id}/stats` is keyed by |
| `started_at` (else `finished_at`) | `created_at_ms` | **Seconds x 1000** |
| which faction contains you, vs `results.winner` | `won` | `None` when there is no winner |
| no winner | `drawn` | |
| — | `speed` | Hardcoded `"cs2"` |
| — | `rated` | Hardcoded `True` |
| — | `moves` | Always `0`; chess-only field |

`_normalize()` returns `None` (match skipped) when the status is not `finished`,
or when the linked `player_id` appears in neither faction.

**The winner is identified two different ways in two different endpoints.**
Here it is a faction key (`"faction1"`). In the match-stats response below it is
a `team_id` UUID. They are not interchangeable, and `_normalize` correctly
compares faction keys.

**Nothing here is filtered by competition type.** A `matchmaking` queue game and
a `championship` game both count. Worth revisiting alongside the chess
eligibility rules, since a private championship is arrangeable.

---

## 4. Per-match stats — `GET /matches/{match_id}/stats`

Called by `faceit.get_match_stats()`, parsed by `_extract_player_metrics()`.
This is where every pool and tournament metric comes from.

```
https://open.faceit.com/data/v4/matches/1-98cf6a9c-.../stats
```

```jsonc
{
  "rounds": [                                  // one entry per map
    {
      "match_id": "1-98cf6a9c-...",
      "match_round": "1",
      "played": "1",
      "best_of": "1",
      "round_stats": {
        "Map": "de_dust2",
        "Score": "13 / 9",
        "Rounds": "22",
        "Winner": "641bc080-6868-4cee-bb4c-044dd05f7d1c",   // a TEAM ID here
        "Region": "EU"
      },
      "teams": [
        {
          "team_id": "641bc080-...",
          "players": [
            {
              "player_id": "e5e8e2a6-...",
              "nickname": "donk666",
              "player_stats": {
                "Kills": "18",
                "Deaths": "14",
                "K/D Ratio": "1.29",
                "Headshots %": "83",
                "ADR": "94.2",
                "MVPs": "4",
                "Result": "1",
                // ~40 more: entry, clutch, utility, flash, sniper, multikills
              }
            }
            // 4 more players
          ]
        }
        // the other team
      ]
    }
  ]
}
```

**The six fields the adapter maps:**

| FaceIt `player_stats` | Our metric | Used by |
| --- | --- | --- |
| `Kills` | `cs2_kills` | — |
| `Deaths` | `cs2_deaths` | — |
| `K/D Ratio` | `cs2_kd_ratio` | Pool, tournament, H2H stat duel |
| `Headshots %` | `cs2_headshot_pct` | Pool, tournament, H2H stat duel |
| `ADR` | `cs2_adr` | Pool, tournament, H2H stat duel |
| `MVPs` | `cs2_mvps` | — |

A field that is absent is **omitted, never guessed**. Every value is a string
and goes through `_to_float()`.

**This is one HTTP request per match.** Polling twenty matches costs twenty-one
requests, against Lichess's one. That is why `get_match_stats()` is TTL-cached
in-process for an hour (finished-match stats never change) and why the API and
the worker each keep their own cache.

`_extract_player_metrics` walks `rounds -> teams -> players` and stops at the
first entry whose `player_id` matches. On a best-of-three only the first map's
stats are read.

---

## 5. What is NOT in the response

**No per-player score.** There is no `Score` field in `player_stats`, which is
why ADR is the contribution metric. The adapter comment says this; the captured
key list confirms it.

**No Elo, and no Elo delta, anywhere in the match feed.** `faceit_elo` exists
only on the player object, as a current value. So a match cannot tell you what
either player was rated when they played it, and any Elo-based matchmaking has
to read the profile snapshot taken at link time.

**No `rated` flag.** Every CS2 match is treated as rated (`rated=True`,
hardcoded). The chess distinction between rated and casual has no equivalent
here, so the `rated_only` filter does nothing for CS2.

**No anti-cheat or ban signal on a match.** `infractions` exists on the player
object only.

**No move or round timeline**, so nothing analogous to the chess
minimum-move rule exists for CS2. The nearest usable signals are
`round_stats.Rounds` (a 22-round match is real; a 3-round one is not) and
`competition_type`.

---

## 6. Reproducing this capture

```bash
export FACEIT_API_KEY=...        # same key the API uses
AUTH="Authorization: Bearer $FACEIT_API_KEY"

# 1. Player (and the player_id everything else needs)
curl -s -H "$AUTH" \
  'https://open.faceit.com/data/v4/players?nickname=YOUR_NICK&game=cs2' | jq

PID=$(curl -s -H "$AUTH" \
  'https://open.faceit.com/data/v4/players?nickname=YOUR_NICK&game=cs2' | jq -r .player_id)

# 2. Lifetime stats
curl -s -H "$AUTH" "https://open.faceit.com/data/v4/players/$PID/stats/cs2" | jq

# 3. History, exactly as the adapter asks for it
curl -s -H "$AUTH" \
  "https://open.faceit.com/data/v4/players/$PID/history?game=cs2&limit=3" | jq

# 4. Per-match stats for the newest match
MID=$(curl -s -H "$AUTH" \
  "https://open.faceit.com/data/v4/players/$PID/history?game=cs2&limit=1" \
  | jq -r .items[0].match_id)
curl -s -H "$AUTH" "https://open.faceit.com/data/v4/matches/$MID/stats" | jq
```

FaceIt rate-limits per key. `request_json()` fails soft, so a throttled poll
degrades to an empty history rather than raising, and `get_player_history()`
returns `[]` on any host error. A settlement that reads an empty history grades
the entry as unverifiable and refunds it, which is the safe direction.

---

## 7. See also

- `docs/game/cs2-demo.md` — what the CS2 demo can and cannot do today, per mode.
- `docs/game/chess.md` — the same capture for Lichess.
