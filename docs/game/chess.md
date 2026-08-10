# Chess (Lichess) — live API responses

Real responses captured on **2026-08-08** by calling Lichess with the exact
parameters `services/hosts/lichess.py` sends. Nothing here is hand-written or
trimmed except where marked, so what you see is what the adapter parses.

Sample account: **`Zhigalko_Sergei`** (an active GM, so recent games always
exist). Swap the username in any URL below to see your own.

Two endpoints are all we use for the read path. No API key, no OAuth.

---

## 1. Profile — `GET /api/user/{username}`

Called by `lichess.get_user()`, parsed by `ChessLichessAdapter._to_profile()`.
Used on link, on refresh, and for your rating badge.

```
https://lichess.org/api/user/Zhigalko_Sergei
```

```jsonc
{
  "id": "zhigalko_sergei",
  "username": "Zhigalko_Sergei",
  "title": "GM",
  "createdAt": 1537451857464,        // epoch ms -> account_age_days
  "seenAt": 1786204473182,
  "url": "https://lichess.org/@/Zhigalko_Sergei",
  "count": {
    "all": 159627,
    "rated": 132904,                 // -> total_games (falls back to `all`)
    "win": 121107,                   // -> win_rate = (win + 0.5*draw) / rated
    "draw": 6447,                    // -> draw_rate = draw / rated
    "loss": 32073,
    "bookmark": 0, "playing": 0, "import": 0, "me": 0
  },
  "playTime": { "total": 19576667, "tv": 5090859 },
  "perfs": {
    "bullet":    { "games": 81325, "rating": 3143, "rd": 45,  "prog": -6 },
    "blitz":     { "games": 17834, "rating": 2808, "rd": 48,  "prog": 13 },
    "rapid":     { "games": 446,   "rating": 2948, "rd": 184, "prov": true },
    "classical": { "games": 0,     "rating": 1500, "rd": 500, "prov": true }
    // also: ultraBullet, correspondence, chess960, atomic, other variants
  },
  "profile": { /* bio, country, links */ },
  "patron": true,
  "streamer": { /* present only for streamers */ }
}
```

**How it maps to `ProfileSnapshot`:**

| Lichess field | Our field | Note |
| --- | --- | --- |
| `username` | `username`, `display_name` | |
| `url` | `url` | |
| `createdAt` | `account_age_days` | Converted from epoch ms |
| `count.rated` (else `count.all`) | `total_games` | Gates `GAME_HISTORY_FLOOR` (chess: 20) |
| `count.win` / `count.draw` | `win_rate`, `draw_rate` | A draw counts as half a win |
| `perfs.{speed}` | `formats[]` | Only speeds with `games > 0` are kept |
| busiest `perfs` entry | `primary_speed` | |

Only the four real time controls are read: `bullet`, `blitz`, `rapid`,
`classical`. Variants (chess960, atomic) and `correspondence` are ignored.

**`rating` here is the Elo you mentioned wanting for matchmaking.** It is
already captured per speed in `formats[]`, so it is available today with no new
fetch.

---

## 2. Games — `GET /api/games/user/{username}`

Called by `lichess.get_user_games()`, parsed by `_normalize()`. This is the
settlement and metric-modelling feed. The response is **NDJSON**, one game per
line, newest first, so the `Accept: application/x-ndjson` header matters.

Exact query the adapter sends:

```
https://lichess.org/api/games/user/Zhigalko_Sergei
  ?since=0        // epoch ms floor; 0 on bootstrap, window start on settlement
  &max=3          // 50 in the adapter; 3 here to keep this doc readable
  &rated=true
  &moves=true     // needed to count plies
  &pgnInJson=false
  &clocks=false
  &evals=false
  &opening=false
```

One full game, unedited apart from truncating the move list:

```jsonc
{
  "id": "LYQqlSc6",
  "rated": true,
  "variant": "standard",             // non-standard is skipped by _normalize
  "speed": "bullet",
  "perf": "bullet",
  "createdAt": 1785963612475,        // -> created_at_ms, used for windowing
  "lastMoveAt": 1785963679139,
  "status": "mate",                  // must be in the _FINISHED allowlist
  "source": "lobby",
  "players": {
    "white": {
      "user": { "name": "SiegfriedvonXanten52", "id": "siegfriedvonxanten52" },
      "rating": 2804,
      "ratingDiff": -1
    },
    "black": {
      "user": { "name": "Zhigalko_Sergei", "title": "GM", "id": "zhigalko_sergei" },
      "rating": 3141,
      "ratingDiff": 2
    }
  },
  "winner": "black",                 // omitted entirely on a draw
  "moves": "d4 Nf6 Nf3 e6 g3 b5 Bg2 Bb7 O-O c5 c4 b4 dxc5 ... Re6#",
  "clock": { "initial": 30, "increment": 0, "totalTime": 30 }
}
```

**How it maps to `NormGame`:**

| Lichess field | Our field | Note |
| --- | --- | --- |
| `id` | `id` | The game id settlement grades against |
| `speed` | `speed` | |
| `rated` | `rated` | |
| `createdAt` | `created_at_ms` | Window filtering uses this |
| `moves` | `moves` | Ply string to full moves: `(plies + 1) // 2` |
| `winner` vs your colour | `won` | `None` when the result is unknown |
| `status` in the draw set | `drawn` | `draw`, `stalemate` |
| **`moves` (count)** | **`metrics["chess_moves"]`** | The pool / tournament stat |

`_normalize()` returns `None` (game skipped) when the status is not finished,
the variant is not standard, or neither player id matches the linked account.

### Statuses treated as finished

`mate`, `resign`, `stalemate`, `timeout`, `draw`, `outoftime`, `cheat`,
`variantEnd`. Anything else (`started`, `created`, `aborted`) is ignored.

---

## 3. What is NOT in the response

This is the important part, and it is why the pool metric is what it is.

**There is no `analysis` field and no accuracy.** The captured game has exactly
these keys and no others:

```
clock, createdAt, id, lastMoveAt, moves, perf, players, rated,
source, speed, status, variant, winner
```

Accuracy appears only when a player has explicitly requested computer analysis
on that game, which is a small minority of games, and it would need
`evals=true` plus a far heavier response. It cannot be a settlement input:
most contests would simply fail to grade.

That is why `chess_accuracy` in `constants.py` never had a data source behind
it, and why the live pool and tournament metric is **`chess_moves`** (moves per
game), which is present on every game at no extra cost.

Caveat worth remembering: moves-per-game is a weak skill proxy, and a player
could inflate it by stalling a won position. Fine for testing; it wants a
sandbagging check before it carries real money at scale.

---

## 4. Other endpoints the adapter uses

| Purpose | Endpoint | Where |
| --- | --- | --- |
| Create a brokered duel | `POST /api/challenge/open` | `create_open_challenge()` |
| Grade a brokered duel | `GET /api/game/export/{id}` | `get_game()` / `match_winner()` |
| Live board for Activity | `GET /api/game/export/{id}` (lighter params) | `get_live_game()` |

Brokered chess is what makes a real head-to-head work: the platform opens a
challenge restricted to the two linked accounts and grades that exact game id.
It also means a fabricated opponent can never play you, which is why the test
head-to-head grades on your next rated game instead.

---

## 5. Reproducing this capture

```bash
# Profile
curl -s -H 'Accept: application/json' \
  https://lichess.org/api/user/YOUR_USERNAME | jq

# Games, exactly as the adapter asks for them
curl -s -H 'Accept: application/x-ndjson' \
  'https://lichess.org/api/games/user/YOUR_USERNAME?since=0&max=3&rated=true&moves=true&pgnInJson=false&clocks=false&evals=false&opening=false'
```

Rate limits are generous but real: Lichess throttles bursts and returns `429`.
`request_json()` fails soft, so a throttled metric bootstrap degrades to an
empty history rather than raising.
