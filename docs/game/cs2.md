# CS2 — what the APIs actually return

Real responses captured on **2026-08-13** against SteamID `76561198748110372`,
using the exact parameters the code sends. Keys and per-user secrets are
redacted; nothing else is edited, so what you see is what the adapter parses.

Two entirely separate systems feed CS2, and confusing them is the first thing
that goes wrong:

| | Steam Web API | Game Coordinator |
| --- | --- | --- |
| Transport | HTTPS + JSON | protobuf over the Steam network |
| Auth | an API key | a signed-in Steam account |
| Reachable from Python | yes | **no** — hence `gc-sidecar/` |
| Gives you | identity, bans, and *which share code comes next* | the **scoreboard** |

The Web API never returns per-match statistics. It will tell you a match
*exists* — that is what the share-code chain is — but the kills, deaths and
headshots a wager settles on come only from the Game Coordinator.

---

## Steam Web API

### `GetPlayerSummaries` — identity, and who is playing right now

```http
GET /ISteamUser/GetPlayerSummaries/v2/?key=<redacted>&steamids=76561198748110372
```

```json
{
  "response": {
    "players": [
      {
        "steamid": "76561198748110372",
        "communityvisibilitystate": 3,
        "personaname": "lifeunicorn",
        "profileurl": "https://steamcommunity.com/profiles/76561198748110372/",
        "avatar": "https://avatars.steamstatic.com/fef49e7f….jpg",
        "avatarmedium": "https://avatars.steamstatic.com/fef49e7f…_medium.jpg",
        "avatarfull": "https://avatars.steamstatic.com/fef49e7f…_full.jpg",
        "avatarhash": "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb",
        "lastlogoff": 1786582724,
        "personastate": 1,
        "primaryclanid": "103582791429521408",
        "timecreated": 1768503605,
        "personastateflags": 0,
        "gameextrainfo": "Counter-Strike 2",
        "gameid": "730"
      }
    ]
  }
}
```

`personaname` is a display name and is mutable — the identity is `steamid`, and
nothing keys off the name.

**`gameid` is load-bearing.** It appears only while the account is in a game,
and `"730"` means CS2. The sidecar supervisor reads it to decide whether it may
connect, because connecting *announces* that the account is playing CS2 and
would evict whoever actually is. The check is a plain read: no sign-in, nobody
evicted.

One trap: while the sidecar is connected, this field reports `730` for that same
account, because from Steam's side the sidecar is playing CS2. The answer only
distinguishes a human from the sidecar while the sidecar is down — which is
exactly, and only, when it is consulted.

### `GetPlayerBans` — checked at link time

```http
GET /ISteamUser/GetPlayerBans/v1/?key=<redacted>&steamids=76561198748110372
```

```json
{
  "players": [
    {
      "SteamId": "76561198748110372",
      "CommunityBanned": false,
      "VACBanned": false,
      "NumberOfVACBans": 0,
      "DaysSinceLastBan": 0,
      "NumberOfGameBans": 0,
      "EconomyBan": "none"
    }
  ]
}
```

A failed lookup returns `None`, which means **unknown** and never *clean* — the
distinction matters, because treating a failed ban check as a pass is how a
banned account gets to stake money.

### `GetUserStatsForGame` — lifetime totals, usually unavailable

```http
GET /ISteamUserStats/GetUserStatsForGame/v2/?appid=730&key=<redacted>&steamid=…
→ HTTP 400
```

**400 is the normal case, not an error.** It is what Steam returns when game
details are not public, which is the default. When it does succeed it carries
lifetime counters (`total_kills`, `total_deaths`, `total_time_played`, …)
aggregated across casual, deathmatch and bot games.

Because of that mixture it is treated as the weakest possible signal: it nudges
a brand-new account's starting bar halfway toward the player and is ignored
entirely once a real match exists. Handling the 400 quietly is required, not
optional — a private profile must not fail a link.

### `GetNextMatchSharingCode` — the chain

```http
GET /ICSGOPlayers_730/GetNextMatchSharingCode/v1/
    ?key=<redacted>&steamid=…&steamidkey=<per-user auth code>&knowncode=CSGO-…
```

Valve stores a player's matches as a linked list. Given one code they own, this
returns the next — which is what removes the paste step.

```json
{ "result": { "nextcode": "CSGO-ZmR9i-fDPS3-GqJEk-ZLEyU-QmztJ" } }
```

The status codes are the whole contract and are **not** interchangeable:

| Status | Meaning | What the code does |
| --- | --- | --- |
| `200` | a newer match exists | resolve it, store it, advance the cursor |
| `202` | caught up | **normal**, and the common case — no body worth reading |
| `412` | `knowncode` is not this player's | stop and re-prompt; retrying can never work |
| `403` | auth code rejected or regenerated | mark the chain broken, tell the player |
| `429` / `5xx` | rate limited or down | back off; leave the cursor alone |

Some responses answer `200` with `"nextcode": "n/a"` instead of `202`. Both mean
caught up.

Getting the permanent failures wrong matters beyond one user: Valve temporarily
blocks an API key that keeps presenting bad auth codes, so one stale cursor
retried in a loop takes settlement down for everybody.

**`steamidkey` is a per-user secret.** It reads that account's match history. It
goes in the query string because Valve accepts nothing else, which is why
request-level URL logging has to stay off — see `logging.py`.

---

## Game Coordinator — the scoreboard

Reached through `gc-sidecar/` over loopback, authenticated with a shared secret:

```http
POST /resolve  { "shareCode": "CSGO-xLsRA-f9V8L-xvMCL-JuvMY-XZrKG" }
```

A share code carries only three ids (`match_id`, `outcome_id`, `token_id`). The
GC turns those into the finished match:

```json
{
  "matchId": "3836649446058229858",
  "matchTime": 1786622320,
  "scores": { "a": 13, "b": 3 },
  "demoUrl": "http://replay129.valve.net/730/00383665256205700324…",
  "players": [
    { "steamid": "76561198728704465", "team": "a", "kills": 17, "deaths": 4,
      "assists": 4, "headshots": 3, "mvps": 3, "score": 39 },
    { "steamid": "76561198307691890", "team": "a", "kills": 15, "deaths": 6,
      "assists": 3, "headshots": 7, "mvps": 4, "score": 32 },
    { "steamid": "76561199095285812", "team": "a", "kills": 11, "deaths": 6,
      "assists": 2, "headshots": 4, "mvps": 4, "score": 24 }
  ]
}
```

Ten entries, one per scoreboard line, **including the nine other players**. That
is not incidental: Valve put those people in the lobby because it thinks they
are your level, so it is a free, continuously updated read on "players around my
rank" without asking any ranking API for anything. Bars are quoted from it.

### Every field available per player

| Field | Type | Notes |
| --- | --- | --- |
| `steamid` | string | SteamID64. The only identity here |
| `team` | `"a"` / `"b"` | maps to `scores.a` / `scores.b` |
| `kills` | int | |
| `deaths` | int | |
| `assists` | int | not currently wagered on |
| `headshots` | int | a **count**, not a percentage |
| `mvps` | int | round MVPs |
| `score` | int | Valve's own scoreboard points |

### What is stored

| Column | From | Notes |
| --- | --- | --- |
| `share_code` | the submitted code | **globally unique** — one match cannot settle ten wagers |
| `match_id` | `matchId` | |
| `match_time` | `matchTime` | decides which contest windows it falls in |
| `rounds_total` | `scores.a + scores.b` | the surrender check reads this |
| `score_a`, `score_b` | `scores` | |
| `players` | `players[]` | the whole array, verbatim |
| `demo_url` | `demoUrl` | |
| `demo_expired` | derived | demos expire after about a month; scoreboards do not |

`map_name` is **null**: the GC's match record does not carry it, and it is only
ever cosmetic here.

### What is derived, and what cannot be

```http
cs2_kd_ratio     = kills / deaths          (deaths 0 → falls back to kills)
cs2_headshot_pct = headshots / kills * 100 (kills 0 → 0.0, not a division error)
cs2_kills        = kills
```

**There is no ADR.** Average damage per round needs per-round damage, which is
in the demo file, not the scoreboard. Until demos are parsed, ADR does not
exist — and a market nothing can grade would take money for a wager that could
never settle, which is why CS2 offers a kills market instead.

Assists, MVPs and Valve's `score` are all available and unused; they are the
cheapest metrics to add if wanted.

---

## Which matches produce a share code at all

Only **Premier, Competitive and Wingman**. Casual, Deathmatch and Arms Race
generate none, so a code that resolves was necessarily a real matchmaking match
— which is why no game-mode filter is needed anywhere.

A completed match runs at least 16 rounds (9 for Wingman, which is 2v2). Below
that it was surrendered or abandoned, and it is refused: not at intake, but in
the adapter every engine reads matches through, so no ingest path can forget.

---

## See also

- `docs/game/cs2-how-it-works.md` — how these pieces fit together end to end
- `docs/game/cs2-steam.md` — the design decisions behind the Steam integration
