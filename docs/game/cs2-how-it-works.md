# CS2, end to end — how a match becomes a payout

Written **2026-08-13**, after the loop ran for real: a wager joined, a match
played, and the pot paid out with nothing pasted by hand. Everything below
describes what the code does today, not what it is meant to do.

For the raw API responses see `docs/game/cs2.md`. For why the Steam design was
chosen see `docs/game/cs2-steam.md`.

---

## The problem CS2 poses

Chess has a public API: ask Lichess what someone played and it tells you. CS2
has nothing of the kind. There is no endpoint that returns a player's match
statistics — not private, not rate-limited, *absent*.

What Valve gives you instead is a **share code**: a 34-character string the
player can copy out of the game, carrying three ids and no statistics. Turning
one into a scoreboard requires the Game Coordinator, which speaks protobuf over
the Steam network, must be talked to by a signed-in Steam account, and has no
maintained Python client.

That single fact shapes everything: the sidecar exists, the chain exists, and
the account conflict exists all because the scoreboard is only reachable by
pretending to be a CS2 player.

---

## The four moving parts

| Part | Runs as | Job |
| --- | --- | --- |
| **API** (`apps/api`) | uvicorn | bars, joining, settlement rules |
| **Worker** | `settlement_worker` | every 15s: collect matches, grade, pay |
| **Sidecar** (`gc-sidecar/`) | node, loopback :8787 | share code → scoreboard |
| **Supervisor** | `supervise.js` | keeps the sidecar up without evicting you |

The sidecar is the only piece that has to be a separate service, and only
because of the protobuf/Steam-account requirement. It is deliberately dumb: it
resolves codes and knows nothing about wagers, money, or users.

---

## Setup, once per player

Three things, in one card (`Cs2SetupCard`), in this order because each depends
on the last:

1. **Sign in through Steam.** OpenID 2.0. The security is entirely in the
   verification round-trip: the callback's parameters are posted *back* to Steam
   with `openid.mode=check_authentication`, and only a literal `is_valid:true`
   is accepted. Without that step anyone could forge a callback and claim any
   SteamID. What is stored is the SteamID64 — never the persona name, which is
   mutable.
2. **A match authentication code**, from Steam's help wizard. Per account, and
   there is no bulk or delegated form, so **every player needs their own**. It
   is not a password and cannot spend anything, but it reads match history, so
   it is stored, never returned by the API, and never logged.
3. **One share code**, as the starting cursor.

The server proves both credentials work before saving them — a cursor stored and
tried later fails at settlement time, which is the worst possible moment to
discover a typo, because money is already staked.

---

## The loop

```
you play a match
        │
        ▼
worker cycle (15s)  ──►  GetNextMatchSharingCode(cursor)
        │                        │
        │                   200 → new code          202 → caught up, done
        │                        │
        ▼                        ▼
   sidecar /resolve  ──►  Game Coordinator  ──►  scoreboard (10 players)
        │
        ▼
   stored in cs2_matches (share_code unique)
        │
        ├──►  baseline refresh — what you are asked to clear next
        │
        ▼
   pool grading: your first qualifying match inside the window
        │
        ▼
   clearers split the pot − rake   |   nobody clears → full refund, zero rake
```

Grading is `value >= room_bar` (or `<=` for metrics where lower is better), so
landing exactly on the bar clears it.

A pool settles when its window ends **or** early, once every entrant is decided.
Early settlement is why a payout lands about a minute after you quit rather than
a day later.

---

## The account conflict, and why it is the hard part

The sidecar signs in as a Steam account, and connecting to the Game Coordinator
means **telling Steam that account is playing CS2**. An account can only do that
in one place. So if the sidecar uses the same account you play on, the two evict
each other.

A supervisor that blindly restarts makes this worse than being down: every retry
kicks you out of the match it exists to grade.

So before connecting, the supervisor asks the Web API whether that account is
already in CS2 (`gameid == "730"`). That is a plain read — no sign-in, no game
announcement, nobody evicted:

- **In game** → wait, re-check every 20s, and say so plainly.
- **Free** → connect. The next worker cycle collects whatever you played.
- **Unknown** (API down, no key) → one retry, then proceed. Staying down because
  Steam had a bad minute is its own failure.

One subtlety that makes the check readable: while the sidecar is connected,
Steam reports *that same account* as in CS2, because the sidecar is playing it.
The answer only tells you apart from the sidecar while the sidecar is down —
which is exactly, and only, when it is asked.

**In production the sidecar should have its own Steam account** that owns CS2.
Then none of this arises. The waiting behaviour exists so a one-account demo
works anyway.

---

## What is refused, and why

Each of these closes a hole that is otherwise trivially exploitable.

| Rule | Without it |
| --- | --- |
| Your SteamID64 must be in the roster | paste a stranger's good match, get paid |
| The match must post-date the wager | paste your best game from last month |
| A share code is globally unique (DB constraint) | one match settles ten wagers |
| At least 16 rounds (9 for Wingman) | a three-round surrender settles a wager |
| Only Premier / Competitive / Wingman produce codes at all | — no filter needed |

The round floor is enforced in the **adapter**, not at intake. Intake checks
guard only the door they are nailed to: a code collected automatically never
passes the paste handler, and neither would any ingest path added later. Every
engine reads matches through the adapter, so a short match is simply never a
match any of them can see. The same floor applies to baselines — otherwise
abandoning games is the cheapest way to lower the bar you are offered.

---

## What you are asked to clear

Bars come from three sources, weighted by how much each is actually worth:

1. **Your own matches** — the only direct evidence, and the noisiest, since CS2
   is 5v5 and one match says as much about your teammates as about you.
2. **Your lobby** — every stored match carries nine other scoreboards, and Valve
   put those people there because it thinks they are your level. A free read on
   "players around my rank" without any ranking API. Uses the **median**, since
   one smurf should not set everyone else's bar. Decays as your own record grows.
3. **A population default**, for an account with no history at all.

Robustness, because a bar decides money:

- The best and worst of your own results are dropped once there are five to
  spare, so one extraordinary game does not set your bar for a month.
- The spread is floored: three consistent games are a small sample, not a
  metronome, and a bar placed off a near-zero spread is unreachable.
- An established baseline can fall at most 8% per match. Tanking is the obvious
  attack on a bar quoted from your own history; this prices it above what any
  single payout is worth. Rising is unlimited — improving is not an exploit.
- Sudden jumps and sustained drops are flagged for review, never auto-blocked.
  An unusual run is evidence, not a verdict.

Metrics: `cs2_kd_ratio`, `cs2_headshot_pct`, `cs2_kills`. **No ADR** — it needs
per-round damage from a demo file, and a market nothing can grade would take
money for a wager that could never settle.

---

## When things break

| Symptom | Meaning | What happens |
| --- | --- | --- |
| `/cs2/health` → `ready:false` | sidecar asleep or waiting for you | a request wakes it; while you play, it waits by design |
| Chain `202` forever | you have not played since | normal |
| Chain state `broken` | 412/403 — bad cursor or dead auth code | stops and asks you to reconnect; never retries |
| Sidecar down mid-collection | GC unreachable | cursor **does not advance**; the match is retried next cycle |
| Match graded unverifiable | no qualifying match in the window | full refund, zero rake — you cannot lose by not playing |

That fourth row was a real bug: the cursor used to advance regardless, so a
sidecar restart silently skipped a match somebody had staked money on. Retryable
failures now stop the walk with the cursor untouched; permanently unresolvable
codes still skip, or one dead code would wedge the chain forever.

---

## Practice opponents

With one real account nothing forms — pools need three to four entrants. So the
demo fills rooms with `testbot_*` users created through the same provisioning
and entered through the same `enqueue()` as anyone else. No engine has a special
case for them.

They never play, so they are graded rather than polled. Most miss; **one clears**
(`testbot_ada`). That matters more than it sounds: with every bot missing, a pool
had only two possible endings — you take everything, or everything refunds. The
rule that actually decides the money, *clearers split the pot*, was unreachable,
and so was losing. One clearing opponent makes both halves demonstrable.

They are excluded from leaderboards and the activity ticker, and
`test_opponents.purge()` removes every one. **This module is scaffolding — delete
it before launch.**

---

## Running it locally

```bash
# 1. sidecar (supervised; needs GC_REFRESH_TOKEN, GC_SHARED_SECRET, GC_STEAM_ID)
cd gc-sidecar && npm start

# 2. api
cd apps/api && uv run uvicorn moneymatch_api.main:app --port 8000

# 3. worker — nothing settles without it
cd apps/api && uv run python -m moneymatch_api.workers.settlement_worker
```

`npm run token` mints the refresh token once, via QR so no password is typed.

Required config: `STEAM_API_KEY`, `GC_SIDECAR_URL`, `GC_SHARED_SECRET`,
`GC_STEAM_ID`, and `VALVE_CHAIN_ENABLED=true` for automatic collection. The
sidecar **refuses to start** without a shared secret — it can read any player's
match history, and a startup warning is not access control.

Run one worker. Two are safe (settlement claims a match before working it, and
a test proves exactly-once) but they double how often you poll Valve, which is
the endpoint that throttles a key for abuse.
