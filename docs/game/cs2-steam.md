# CS2 on Steam — what was built and how it works

Written 2026-08-11, on branch `feat/csgo_testing`. This is the CS2 wager loop:
sign in through Steam, play a real matchmaking match, paste one share code, and
the wager settles from Valve's own scoreboard.

Companion documents:

- `cs2.md` — the FaceIt API capture (the path this replaces)
- `cs2-demo.md` — what the FaceIt demo could and could not do
- `cs2-baseline-2026-08-11.md` — the before picture

---

## The one insight the whole design rests on

**You do not need to download or parse a demo file to settle a wager.**

When the Game Coordinator resolves a share code, the reply already contains the
final scoreboard: per-player kills, deaths, assists, headshots, MVPs, and the
team scores. That is enough to grade three metrics directly.

| Metric | From the scoreboard? |
| --- | --- |
| K/D ratio | yes |
| Headshot % | yes (headshots ÷ kills) |
| Kills | yes |
| Match result | yes (team scores) |
| **ADR** | **no — needs a parsed demo** |
| **KAST, opening duels, clutches** | **no — needs a parsed demo** |

So `cs2.steam` ships **K/D, headshot % and kills**, and `cs2_adr` is
deliberately absent from its registry. A market you cannot grade is worse than
three you can. ADR comes back if and when demo parsing is built.

---

## The flow, in plain English

1. **You sign in through Steam.** One click. Steam tells us your SteamID64,
   which is the only identity Valve actually vouches for.
2. **You join a wager** — solo pool, tournament or head-to-head. Nothing here is
   CS2-specific; the same engines run chess.
3. **You play a real CS2 match.** Premier, Competitive or Wingman.
4. **You paste the share code.** In game: *Watch → Your Matches → copy share
   code*.
5. **The server resolves it** through the Game Coordinator, checks it is really
   your match, stores the scoreboard, and the wager settles.

Only step 4 is new work for the player, and phase 4 (not built) would remove it.

---

## Why a share code, and why only some matches count

CS2 has **no public per-match stats API**. The share code is the only artifact a
player can copy out of the game, so it is the unit of intake.

**Casual, Deathmatch and Arms Race produce no share code at all.** Only Premier,
Competitive and Wingman do. That is not a limitation to work around, it is free
mode filtering: if a code resolves, it was a real matchmaking match. No separate
eligibility rule is needed.

For testing, **Wingman is the fast one**: 2v2, first to 9, about 15 minutes,
against 40+ for Premier.

---

## What was built

### Share code codec — `services/sharecode.py`

A share code is base-57 over 144 bits, unpacking little-endian into three
fields: `match_id` (u64), `outcome_id` (u64), `token_id` (u16). All three are
needed to ask the GC about a match.

The module implements **encoding as well as decoding**, purely so the codec can
be round-trip tested. This matters more than it sounds: a decoder that drifts
does not fail loudly. It produces a *different valid-looking* match id, and
settlement quietly grades the wrong match. 23 tests, including a 200-iteration
random round trip.

> **Not yet validated against a real code.** Round-tripping proves the codec is
> self-consistent, not that it agrees with Valve. The first real share code is
> the moment we find out.

Rejection messages name the in-game path rather than saying "invalid", because
the most likely cause is a player looking in the wrong place.

### Steam Web API client — `services/hosts/steam.py`

Live-verified against a real key.

- **`GetPlayerBans`** at link time. Cheap, and you want it before money moves.
- **`GetUserStatsForGame`** (appid 730) for a lifetime K/D prior, used to
  bracket a user who has no history with us yet.
- **`GetPlayerSummaries`** for display name and avatar.
- **`ResolveVanityURL`** for pasted profile links — *custom profile URLs only*.

Two deliberate behaviours:

**An unavailable ban lookup returns `None`, never "clean".** On a product where
money moves on that answer, *unknown* and *no bans* must not be the same value.

**The lifetime prior is hedged hard.** It needs the profile's *Game details* to
be public, and both accounts tested while building this kept them private, so
**the fallback is the normal path, not the edge case**. It is also cumulative
across casual, deathmatch and bot games, so it is a weak signal and is never
shown as a skill rating.

Display names are refused as identity everywhere. They are mutable, non-unique
and unsearchable — a straightforward impersonation vector on a wager product.

### Steam OpenID sign-in — `services/steam_openid.py`

Steam never implemented OpenID Connect, so this is OpenID 2.0. The security of
the whole thing is one step:

> the callback's parameters are sent **back to Steam** for verification.

Anyone can craft a URL that looks like a Steam callback naming any SteamID.
Reading the SteamID out of `claimed_id` without that round trip would let anyone
sign in as anyone.

### Storage — `models/cs2.py`, migration `0020_cs2_matches`

One row per resolved match, keyed by share code.

`share_code` carries a **unique index**. That is the only place the "one match
settles one wager" rule cannot be raced: two concurrent submissions would slip
past any application-level check.

Storing the scoreboard, rather than fetching it at settlement time, keeps a
stateful and rate-limited Steam service off the critical path. Resolve once,
grade forever.

### Intake — `services/cs2_submission.py`

Four checks stand between "a code was pasted" and "a wager pays out". Each
closes a hole that is otherwise trivial, and each returns a message the player
can act on:

| Check | Without it |
| --- | --- |
| The code must decode | Malformed input reaches the GC |
| Your SteamID64 must be in the roster | Paste a stranger's good match, get paid |
| The match must post-date the wager | Paste your best game from last month |
| The code must not already be recorded | One good match settles ten wagers |

Plus a **round floor**: 16 rounds normally (13-3 is the shortest legitimate
Premier or Competitive scoreline), 9 for Wingman. The mode is told apart by
roster size. Below the floor the match was surrendered or abandoned.

"Invalid" is not an error message. "You were not in that match. Paste a share
code from a match you played on this Steam account" is.

### Game Coordinator client — `services/gc_client.py`

A share code contains three ids and nothing else. The scoreboard and demo URL
come from Valve's Game Coordinator, which speaks protobuf over the Steam network
rather than HTTP and has no maintained Python client. The bridge is a Node
sidecar; this is the wrapper over it.

The GC is stateful and rate limited, so the client adds a timeout and a
**circuit breaker**: after three consecutive failures it stops calling for 30
seconds, so a wedged GC degrades to a clear error instead of hanging every
request behind it.

**A missing demo URL is normal.** Valve keeps demos about a month. `expired`
does not block settlement — the scoreboard is what grades, and it is still
there. Only the parse-only metrics are lost with it.

### The adapter — `adapters/cs2_steam.py`

Reads stored matches for a SteamID64 and returns them as ordinary `NormGame`s.

This is the join. Once a match is stored, **it is just match history**, and the
existing pool, tournament and head-to-head engines grade it exactly as they
grade a chess game. Intake is the only CS2-specific step in the entire system.

### The demo escape hatch — phase 0

`POST /demo/simulate_result` injects a finished match; `POST /demo/force_settle`
settles one contest immediately (a tournament otherwise waits 48 hours). Both
admin-only *and* behind `DEMO_SIMULATE_ENABLED`.

The property that makes it honest: an injected result enters at the **same seam**
a real one does — `registry.get(game).poll_eligible_games()` — so there is no
`if simulated` branch in grading, the engines or the payout path. The moment
there were one, a green demo would stop being evidence that the real path works.

Verified end to end against the live database: a room formed with three practice
opponents, an injected match graded as a clear while they missed, and the pool
settled with **$10 escrow → $36 payout on a $40 pot**.

### Frontend — `components/cs2/SubmitMatchCard.tsx`

Lives on Activity, which is where you land after playing. Before a Steam link
exists it shows the sign-in button instead of a text box: the SteamID is what
ties a match to you, so asking for a code first would only fail later with a
worse message.

Server rejections are surfaced verbatim. A successful submission invalidates the
pool, tournament, activity and wallet queries, because the match may have just
settled a contest and moved money.

---

## API surface

```
GET  /api/v1/cs2/steam/login-url    where to send a user to sign in
POST /api/v1/cs2/steam/callback     verify the callback, bind the SteamID64
POST /api/v1/cs2/sharecode          paste a code, resolve, verify, store
GET  /api/v1/cs2/health             is the GC sidecar up

POST /api/v1/demo/simulate_result   inject a result      (admin + flag)
POST /api/v1/demo/force_settle      settle now           (admin + flag)
```

---

## What is not built

**The GC sidecar itself.** The implementation prompt said `gc-sidecar/server.js`
was supplied; it is not in the repo. It needs writing, and it needs a
`GC_REFRESH_TOKEN` from a Steam account that has played CS2 (`npx steam-session`
once — not a password and Guard code, which expire in ~30 seconds and will not
survive a restart).

**Until the sidecar exists, `/cs2/sharecode` rejects with "could not reach the
CS2 match service".** Everything behind it — codec, checks, storage, adapter,
settlement, UI — is built and tested.

**FACEIT removal.** `cs2.steam` was registered *alongside* `cs2.faceit` rather
than replacing it. The prompt says remove FACEIT first, but that is ~25 API
references, ~38 web references, ~30 test files and live database rows; doing it
before the Steam path existed would have broken every CS2 test with nothing to
replace them. Same end state, tree stays green throughout.

**Phase 4, automatic share codes — shipped 2026-08-12.** See *Automatic
collection* below.

**Phase 5, demos.** Download, parse, ADR, tamper-proofing, two-chain
verification. Tickets only. Until this exists there is no ADR, which is why CS2
offers a kills market instead — a market nothing can grade would take money for
a wager that could never settle.

---

## Automatic collection

Pasting a code after every match is fine for a demo and hopeless as a product.
Valve stores a player's matches as a linked list, so `GetNextMatchSharingCode`
turns one code they own into the next, forever. A cursor is all that persists
(`cs2_share_chains`, one row per user).

Setup is three things, once: sign in through Steam, create a **match
authentication code**, and name any one match as the starting cursor. All three
live in a single card, because the steps are not independent — the auth code is
meaningless without the link, and the cursor is meaningless without both.

**Every player needs their own authentication code.** It is issued per Steam
account and reads only that account's history, so nobody's code covers anyone
else. It is not a password and cannot spend anything, but it is a secret: stored
and never returned by the API, which reports whether a chain is connected rather
than what it was connected with.

The status codes are the entire contract and are not interchangeable:

| Code | Meaning | What happens |
| --- | --- | --- |
| `200` | a newer match exists | resolve it, store it, advance the cursor |
| `202` | caught up | **normal**, and the common case — not an error |
| `412` | cursor is not this player's | stop and re-prompt; retrying can never work |
| `403` | auth code rejected | chain marked broken until they reconnect |
| `429`/`5xx` | rate limited or down | back off, cursor untouched, chain stays healthy |

Getting the permanent failures wrong matters beyond one user: Valve temporarily
blocks an API key that keeps presenting bad auth codes, so a single stale cursor
retried in a loop would take settlement down for everyone.

A walk is capped at `MAX_CODES_PER_SYNC`, so a player returning after a long
absence catches up over successive syncs instead of stalling a worker cycle. The
sync runs *before* pools settle: a match played minutes before a window closes
has to be in the database by the time that pool is graded, or it grades as
unverifiable and refunds a wager the player won.

Off by default behind `VALVE_CHAIN_ENABLED`.

---

## How to test it

```bash
# Everything that does not need the GC
apps/api/.venv/Scripts/python.exe -m pytest tests/test_sharecode.py \
    tests/test_steam_host.py tests/test_cs2_steam_intake.py \
    tests/test_demo_escape_hatch.py -q

# The demo escape hatch, end to end, money moving
DEMO_SIMULATE_ENABLED=1 apps/api/.venv/Scripts/python.exe \
    scripts/demo/verify_escape_hatch.py

# All three contest modes against the live database, rolled back
apps/api/.venv/Scripts/python.exe scripts/demo/cs2_dryrun.py
```

Once a real share code exists, the first thing to check is whether the decoded
`match_id` is one Valve recognises. That is the single assumption round-trip
testing cannot cover.

---

## Environment

```
STEAM_API_KEY=              # steamcommunity.com/dev/apikey
STEAM_OPENID_REALM=         # must be a prefix of the return URL
STEAM_OPENID_RETURN_URL=
GC_SIDECAR_URL=             # loopback only
GC_SHARED_SECRET=           # the sidecar can read anyone's match data
DEMO_SIMULATE_ENABLED=      # off except during a demo
```

A note that cost an hour: a `.env` line written as `STEAMAPI = value`, with
spaces around the `=`, exports a variable whose **name has a trailing space** and
whose value is empty. It reads as unset. No spaces.

---

## What you cannot claim on stage

**CS2 is 5v5.** Your K/D depends on nine other people, four of whom want you to
fail and four of whom can carry you. A solo-pool bar quoted from your own history
still works as a self-comparison, but the variance is not all yours, and
stacking with friends is a legitimate way to move your own average.

**Head-to-head is coordinated, not brokered.** No API can put two players in the
same Valve matchmaking lobby. Each plays their own next match and the two results
are compared. Do not write copy implying the platform matched them together — it
cannot.
