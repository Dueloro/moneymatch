# Implementation Prompt — CS2 Wagers, Steam-Only, Ship Today

> Paste to a coding agent running inside the repo. Execute top to bottom.
> The phase gates are not advisory.

---

## The key insight — read this before planning anything

You do **not** need to download or parse a demo file to settle a wager today.

When the Game Coordinator resolves a share code, the response already contains
the **final scoreboard**: per-player kills, deaths, assists, headshots, MVPs and
the team scores. That is enough to grade K/D and headshot-percentage wagers
directly, with no `.dem` download, no bz2 decompression, no parser, no object
storage, and no queue.

| Metric | Available from GC scoreboard? |
| --- | --- |
| K/D ratio | ✅ yes |
| Headshot % | ✅ yes (headshots ÷ kills) |
| Kills / Deaths / Assists | ✅ yes |
| Round win/loss, match result | ✅ yes (team scores) |
| **ADR** | ❌ needs demo parse |
| **KAST, opening duels, clutches** | ❌ needs demo parse |

**So: ship K/D and HS% today. Demo parsing is a later phase that unlocks ADR
and tamper-proofing.** This collapses roughly a week of work into an afternoon.
Do not let anyone talk you into building the parse pipeline first.

## Mission

By end of today, a user must be able to:

1. **Sign in through Steam** — one click, nothing typed
2. Join a wager — solo pool, tournament, or head-to-head
3. Be matched with bot opponents at a plausible skill level
4. Play a **real CS2 matchmaking match** (Premier, Competitive or Wingman)
5. Paste one share code — or have it fetched automatically — and see the wager
   settle from real stats

## Non-negotiable rules

1. **Read before you edit.** Confirm every file path and function signature in
   the real code before changing it. If reality contradicts this document,
   trust the code and say so.
2. **Phase gates are real.** Do not start N+1 until N's Definition of Done
   passes. Phases 0–3 are the product. Phases 4–5 are upside.
3. **Rip FACEIT out cleanly, do not half-remove it.** See phase 1.
4. **No silent failures.** Every `except`/`catch` logs with context.
5. **Commit per phase** on a branch, with the phase number in the message.

## ⚠️ Casual matches produce nothing

CS2 generates share codes and demos **only** for Premier, Competitive and
Wingman. Casual, Deathmatch and Arms Race produce **no share code, no demo, and
no stats anywhere**. There is no unranked mode that yields gradeable data.

Useful consequence: **this filters game modes for you for free.** If a share
code resolves at all, it was a real matchmaking match. You do not need a
separate mode-eligibility rule.

For testing, **Wingman is the fast one** — 2v2, first to 9, ~15 minutes, versus
40+ for Premier. Use it for every dry run.

---

# PHASE 0 — Safety net (30 min)

Build the escape hatch before the features, while you still have time.

stay within this current branch on github called feat/csgo_testing

**`POST /api/v1/demo/simulate_result`** — injects a finished, gradeable match
for a user with no external call. It must write through **the same path the
real settlement worker reads**; no downstream special-casing. Gate behind an
admin check plus `DEMO_SIMULATE_ENABLED`. Log loudly, including in the response
body, so a simulated settlement can never be mistaken for a real one.

**`POST /api/v1/demo/force_settle`** — runs settlement for one contest
immediately. Tournaments otherwise settle only at their window close, and you
cannot wait for that on stage.

**DoD:** both work end to end with money moving; both off unless
`DEMO_SIMULATE_ENABLED=1`; committed.

---

# PHASE 1 — Steam identity replaces FACEIT (90 min)

## 1.1 Sign in through Steam

Steam OpenID 2.0. `python-social-auth` has a Steam backend, or hand-roll the
`check_authentication` verification — it is about 40 lines. Returns SteamID64.

**SteamID64 becomes the primary key for every CS2 identity in the system.**

Never accept a Steam **display name** as identity. They are not unique, not
searchable through any API, and freely mutable — on a wager product, accepting
one is a straightforward impersonation vector. `ResolveVanityURL` (custom
profile URLs only) is acceptable as a convenience for pasted profile links.

## 1.2 Rip out FACEIT

Delete or disable, and remove from the game registry:

- `services/hosts/faceit.py`
- `adapters/cs2_faceit.py`
- FACEIT branches in `services/markets.py`, `constants.py`, `routers/demo.py`

Register a new game key **`cs2.steam`**. Grep the whole repo for
`cs2.faceit`, `faceit_elo`, `host_username` and `FACEIT` and deal with every
hit. Leaving a half-removed adapter behind is how you get a demo-morning
`NotImplementedError`.

Keep chess untouched and regression-test it — you are editing shared registries.

## 1.3 Seed a skill prior without match history

New users have no history in your system. You still need a number to bracket
bot opponents against. Two sources, in order:

**a. Steam Web API lifetime stats** — `ISteamUserStats/GetUserStatsForGame`
with `appid=730` returns `total_kills`, `total_deaths`, `total_time_played` and
per-weapon counters. `total_kills / total_deaths` is a usable lifetime K/D
prior. Caveats to encode, not ignore: it is cumulative across casual, DM and
bot games, and it requires the profile's *Game details* to be public. Handle
private profiles by falling back to a default prior and flagging the user
`provisional`.

**b. `POST /recent` on the GC sidecar** (phase 2) — the last 8 matches, if
Valve answers. **Opportunistic only.** Valve has restricted this endpoint over
time and there is an open upstream issue asking whether it still works. Never
put it on a critical path; a failure is normal and must fall through silently
to (a).

Also call `ISteamUser/GetPlayerBans` at link time and store VAC/game ban status.
Cheap, and you want it before money moves.

## 1.4 Make bot opponents track the prior

Your pitch is "matched with players of similar skill." Seed bot opponents'
ratings in a band around the user's prior (±0.15 K/D is a sensible start) so the
claim is literally true and visible in the UI. Confirm the bracketing code
actually *reads* the prior — a correct prior that nothing consumes still looks
wrong on screen.

**DoD:** Steam login yields SteamID64; ban status stored; a lifetime-K/D prior
exists (or a flagged default); no `cs2.faceit` references remain; bot opponents
cluster near the user; chess unaffected; committed.

---

# PHASE 2 — GC sidecar (60 min)

A share code does **not** contain a demo URL or a scoreboard. Both come from
Valve's Game Coordinator: protobuf over the Steam network, not HTTP. There is no
maintained Python client. The bridge is a small Node service.

**`gc-sidecar/server.js` is supplied — read it, do not rewrite it.** It exposes:

```
POST /resolve  { shareCode }  -> { matchId, matchTime, demoUrl, scores, players[] }
POST /recent   { steamId }    -> last 8 matches         [opportunistic]
GET  /health                  -> { ready, queueDepth }
```

## Bot account setup — start this FIRST, it has a lead time

- A Steam account that has **played CS2**. A brand-new account is *limited* and
  may fail to connect to the GC; if you only have a fresh one, spend the $5 to
  unlock it now rather than discovering this at hour eleven.
- Authenticate with a **refresh token** (`npx steam-session` once →
  `GC_REFRESH_TOKEN`), not a password + Steam Guard code. Guard codes expire in
  ~30 seconds and will not survive a service restart.
- Bind to `127.0.0.1` only, behind `GC_SHARED_SECRET`. This service can read
  match data for arbitrary users; it must never face the internet.

## Rules the sidecar already enforces — do not "optimise" them away

- **One GC request in flight at a time**, with ~1.2 s spacing. The GC is
  stateful and rate limited; concurrent requests get throttled, dropped, or
  mismatched to the wrong response.
- **Restart on Steam error** rather than limping in a half-connected state.
- `expired: true` when no demo URL is present. This is normal and expected —
  Valve keeps demos ~1 month — and **it does not block settlement**, because the
  scoreboard is still there. Only ADR/KAST are lost.

## Python client

Add `services/gc_client.py`: a thin `requests` wrapper with a timeout, retry on
`503 gc_not_ready`, and a circuit breaker. Surface `/health` on your own status
page so you can see at a glance whether the GC is up.

**Verify:** with a real share code from your own history, `/resolve` returns a
scoreboard whose kills/deaths match what you see in-game.

**DoD:** sidecar runs, survives a restart, resolves a real share code, Python
client wraps it, committed.

---

# PHASE 3 — The wager loop (2–3 h) ← **the product**

## 3.1 Metric registry

In `constants.py`, define for `cs2.steam`:

- `cs2_kd_ratio` — kills ÷ deaths, from the GC scoreboard
- `cs2_headshot_pct` — headshots ÷ kills × 100, from the GC scoreboard
- `cs2_kills` — raw kills, from the GC scoreboard

**Remove `cs2_adr` from the active registry for now.** You cannot compute it
without parsing a demo. Shipping a market you cannot grade is worse than
shipping three you can. Add it back in phase 5.

All three are rates where **higher is better**, so a harder tier asks for
**more** — the opposite of the chess `moves` metric. Bars are plain
`mu + k*sigma` on a normal.

## 3.2 Result intake — two tiers

**Tier 1 — paste a share code (build this, it is the whole demo).**

Zero setup. After the match the user opens CS2 → **Watch** → **Your Matches**,
copies the share code, and pastes it into the wager. Your backend calls
`/resolve` and settles. No authentication code, no cron, no chain. Works for
any user from the moment they sign in.

**Tier 2 — automatic (phase 4).** Removes the pasting forever.

Ship Tier 1 today. Tier 2 is a UX upgrade on top of the same settlement code —
it only changes *where the share code comes from*.

## 3.3 Anti-fraud — three checks, near-free, do them now

You said verification comes later. These three are cheap enough that skipping
them is not a saving, and each closes an obvious hole:

1. **The wagering user's SteamID64 must appear in the match roster.** Otherwise
   I paste a stranger's good match and get paid.
2. **`matchTime` must be after the wager was joined.** Otherwise I paste my
   best game from last month.
3. **Share codes are globally unique** — a DB unique constraint. Otherwise one
   good match settles ten wagers.

Reject with a clear, specific user-facing reason for each. "This match was
played before you joined the wager" is a good error; "invalid" is not.

Also add a **round floor**: sum the team scores and reject anything under 16
(a 13–3 win is the shortest legitimate Premier/Competitive match; use 9 for
Wingman). This stops a 3-round surrender from grading as a real match.

## 3.4 Settlement

Grading reads the resolved scoreboard, extracts the wagered metric for the
user's SteamID64, and compares against the room bar. Bot opponents never play,
so they grade as a miss and their entries fund the clearers.

Wire all three modes: solo pool, tournament, head-to-head.

**Head-to-head is coordinated, not brokered.** You cannot put two users in the
same Valve matchmaking lobby — no API does that. Each plays their own next
match and the two results are compared. Do not write UI copy implying otherwise.

## 3.5 Full dry run

Sign in → join a solo pool → play a **Wingman** match → paste the share code →
watch it settle. Do this at least twice, end to end, before you stop for the
day. If you only do one thing after phase 3's code is written, do this.

**DoD:** three metrics live; Tier 1 paste-to-settle works; three fraud checks
enforced with clear errors; all three wager modes settle; **two clean end-to-end
runs on a real match**; committed.

> ### 🛑 HARD GATE
>
> If phase 3 is not done, **stop and rehearse**. Phases 4–5 are invisible to a
> demo audience. A polished 0–3 beats a broken 0–5.

---

# PHASE 4 — Automatic share codes (2 h) — flag `VALVE_CHAIN_ENABLED`

Removes the paste step. One-time setup, then every future match arrives on its
own.

**Onboarding — about 90 seconds:**

1. User visits
   `https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128`
   → **Game Authentication Codes** → **Create Authentication Code**. Deep-link
   this button; do not make them navigate Steam support themselves.
2. They paste the auth code, plus **one** share code as a starting cursor —
   which they already know how to find from Tier 1.

**Then poll** `ICSGOPlayers_730/GetNextMatchSharingCode/v1/` with
`key`, `steamid`, `steamidkey`, `knowncode`. Handle the codes properly:

| Code | Meaning | Action |
| --- | --- | --- |
| `200` | next share code returned | store it, advance cursor |
| `202` | caught up | **normal, not an error** |
| `412` | knowncode is not this user's | **stop, re-prompt — never retry** |
| `403` | bad auth code | mark link broken, notify user |
| `429`/`503` | rate limited | exponential backoff |

Repeated bad auth codes get your API key temporarily blocked.

Persist every code and a per-user cursor. Feed new codes into the **same**
`/resolve` → settle path from phase 3. Nothing downstream changes.

**Worth starting today even unused:** share codes never expire, but the demos
they point at do (~1 month). Codes you do not collect now are ADR you can never
compute later.

---

# PHASE 5 — Demos, later

Tickets only. Do not start today.

- **Download and store** the `.dem.bz2` from `demoUrl` on resolve
  (~50–150 MB each). The stored demo is your audit trail — the artifact you
  show a user who disputes a payout. Must happen inside the ~1 month window.
- **Parse worker** — `demoparser2` in a queue. Unlocks ADR, KAST, opening
  duels, clutches. It yields events and ticks, not stats; the metrics are yours
  to compute. Budget days for numbers that match what csstats.gg shows.
- **Tamper-proofing.** The GC scoreboard is Valve-attested and good enough to
  settle on, but the demo is the artifact that survives a dispute.
- **Two-chain verification.** Once both parties are enrolled with auth codes,
  the same match appears in **both** of their chains. Two independent
  Valve-attested chains containing the same `match_id` proves they played each
  other — before parsing anything. This is the endgame for brokered duels.

---

# Demo runbook

**Night before**

- [ ] Bot account logged in, `/health` returns `ready: true`, survives a restart
- [ ] `DEMO_SIMULATE_ENABLED=1`; `VALVE_CHAIN_ENABLED` off
- [ ] **A real share code from a recent match, tested and in your pocket**
- [ ] Full dry run start to finish
- [ ] `git tag demo-ready`

**On stage, safest first**

1. Sign in through Steam — one click, real profile and ban status appear
2. Join a solo pool — bots at similar skill, escrow, live bar
3. Head-to-head and tournament (settle the tournament with `force_settle`)
4. Paste the pre-played share code → real scoreboard → wager settles
5. Live match only if you genuinely have 15+ spare minutes — and make it Wingman

**If it breaks:** `simulate_result`. Say plainly that you are injecting a result
to show the settlement path. An audience forgives a stubbed input far more
readily than a demo that hangs.

**Most likely failure, in order:** bot account limited or not connected to GC →
share code from a casual match (produces nothing) → demo expired (settles fine
anyway, scoreboard is still there) → GC rate limiting from concurrent requests.

---

## Report when done

1. Which phases reached Definition of Done
2. Anything here that contradicted the real code, and what you did about it
3. Every remaining `cs2.faceit` reference, if any
4. Exact commands to run the demo, and the exact rollback command
