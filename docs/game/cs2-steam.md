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

---

# Going to production

Written **2026-08-13** while auditing this branch for a merge into `main`
(Vercel for the web app, Render for the API, Supabase for auth). Everything
below was checked against the code and the deploy config rather than
remembered.

## What actually gets deployed

`render.yaml` declares three things now:

| Service | Type | Why |
| --- | --- | --- |
| `moneymatch-postgres` | database | schema, reconciled on every boot |
| `moneymatch-api` | web | the API, and the settlement worker in-process |
| `moneymatch-gc` | **private** service | share code → scoreboard |

The sidecar was the gap this audit found: it was not deployed at all. Without
it, `POST /cs2/sharecode` and every automatic collection fail at the transport,
so **no CS2 wager can settle** — while the rest of the product looks completely
healthy. That is the worst shape a failure can take, because nothing alerts and
the first symptom is a player asking where their money is.

It is a **private** service deliberately: it can read match data for arbitrary
Steam players and must never be routable from the internet. Two consequences:

- It binds `0.0.0.0` inside the container (`GC_BIND_HOST`), because loopback is
  unreachable from the API container. Private networking is what makes that
  safe, and the shared secret is the second lock, not the first.
- `GC_SHARED_SECRET` comes from the **shared env group** on both services. Two
  independently-set copies drift, and the failure is a 401 on every settlement.

`GC_SIDECAR_URL` is wired from the private service's `hostport`, which Render
hands over as a bare `host:port`. The client fills in a missing scheme, because
httpx rejects a URL without one.

## The worker

`RUN_WORKER_IN_PROCESS=true` runs settlement inside the API container. Nothing
settles without it, and the same switch drives share-code collection, so one
setting governs both.

Run exactly one. Concurrency is *safe* — a match is claimed before it is worked,
and a test proves exactly-once — but every extra instance doubles how often you
poll Valve, and that endpoint throttles a key for abuse.

## Migrations

Applied by `docker-entrypoint.sh` before the app starts, so a deploy that
forgets them is not a failure mode. Verified for this branch: **all 22
migrations apply to an empty schema and land on `0022`**, and `alembic check`
reports no drift afterwards. That check runs in CI, so a model/migration
mismatch fails the build rather than the deploy.

One migration can refuse to run. `0022_retire_cs2_faceit` aborts if any
`cs2.faceit` contest is still in flight, and `set -e` turns that into a failed
deploy rather than a started container. That is deliberate: the alternative is
deleting the scaffolding under an open contest and stranding its entries in
escrow. If it fires, cancel those contests through the engine — which writes the
refund ledger entries — then redeploy.

## Configuration that breaks production if left at its default

| Setting | Default | What happens if unchanged |
| --- | --- | --- |
| `STEAM_OPENID_REALM` | `http://localhost:5173` | Steam returns users to localhost; sign-in silently cannot complete |
| `STEAM_OPENID_RETURN_URL` | `http://localhost:5173/auth/steam/callback` | same |
| `WEB_ORIGIN` | `http://localhost:5173` | CORS refuses the Vercel domain; every browser request fails |
| `GC_SIDECAR_URL` | `http://127.0.0.1:8787` | wired from the private service; unset means no CS2 wager settles |
| `VALVE_CHAIN_ENABLED` | `false` | collection is off, and the paste box has been removed from the UI, so **turn this on** |
| `STEAM_API_KEY` | unset | ban checks and the chain both stop; linking degrades rather than failing |

The realm and return URL are the dangerous pair: nothing errors, Steam simply
returns the user to a host that is not the deployment.

## What is off in production, and stays off

Verified by building the app with a production environment and reading the
resulting route table:

- **`/api/v1/demo/*` is not mounted.** `DEMO_LOGIN_ENABLED` defaults to false.
  With it on, anyone who finds the endpoint is signed in as the shared demo
  account, so it must never be set next to anything real.
- **`/api/v1/dev/e2e/token` is not mounted.** Double-gated on
  `E2E_AUTH_ENABLED` *and* `env != prod`, with the handler re-checking both. It
  mints arbitrary auth tokens, so one gate would not be enough.
- **Injected results are impossible.** `DEMO_SIMULATE_ENABLED` defaults to
  false, and with it off the adapter wrapper is never constructed.
- **Practice opponents cannot appear.** `test_opponents.is_enabled()` keys off
  *who is playing* — the shared demo account — not an environment flag. A real
  signup never sees a fabricated opponent in any environment. Removing demo
  login removes them with it, and `purge()` deletes every row.

`/api/v1/wallet/demo-deposit` **is** mounted in production. That is consistent
today because of the next section, and it is the first thing that has to change
when it stops being true.

## The honest state of "production"

**Every wallet is created with `currency="DEMO"`, including a real signup's.**
There is no real-money path in this codebase: no payment processor, no payouts,
no KYC gate on withdrawal. "Production" today means *the real code paths running
against real Steam accounts with play money*, which is what a public demo needs
and is not the same thing as taking deposits.

What that buys: everything a real user does is the real path. Steam OpenID
verification, the Game Coordinator, the chain, grading, escrow, rake, the ledger
and settlement are identical. Only the currency is fake.

What has to happen before it is not: a payment processor and real deposits,
withdrawal KYC, removing `demo-deposit`/`demo-withdrawal`, deleting
`test_opponents.py` and its three call sites, and a licensing position on
skill-based wagering per state — the geo-fence is enforced, but the list it
enforces is a placeholder.

## Demo account versus a real signup

| | Demo account | Real signup |
| --- | --- | --- |
| Sign-in | `POST /demo/login`, no password | Supabase (Google, or email + password) |
| Opponents | practice bots fill the room | other real players only |
| Room formation | immediate | needs 3–4 real entrants in the same bucket |
| CS2 identity | real Steam OpenID | identical |
| Match data | real Game Coordinator | identical |
| Settlement, escrow, rake | identical | identical |
| Currency | DEMO | DEMO (see above) |

The gap that matters is **room formation**. A pool needs three to four entrants
in the same game/metric/difficulty/entry bucket. The demo hides that with bots;
production does not. Until there is concurrent traffic, real users will queue
without matching — a liquidity problem rather than a bug, and the reason the
practice-opponent scaffolding exists at all.

## Per-user CS2 setup in production

Each player does this once, and it cannot be done for them:

1. **Link Steam.** OpenID, verified by round-trip.
2. **Create a match authentication code.** Issued per Steam account, so **every
   player needs their own** — there is no bulk or delegated form. Stored, never
   returned by the API, never logged.
3. **Paste one share code** as a starting cursor.

After that their matches arrive on their own. The sidecar's Steam account is
**not** any of theirs: it needs its own account that owns CS2, which nobody
plays on. Sharing an account with a player means each side evicts the other from
the Game Coordinator; the supervisor's wait-for-you-to-finish behaviour exists
so a one-account *demo* works, not as a production design.

## Failure modes, and what a player sees

| What breaks | Player sees | Recovers by |
| --- | --- | --- |
| Sidecar down | matches stop being collected | the supervisor restarting it; the cursor is untouched, so nothing is skipped |
| Sidecar not deployed | the same, permanently | deploying it — nothing else surfaces this |
| Valve rate limits | nothing; collection pauses | backing off automatically |
| A player's auth code revoked | the chain reads "Disconnected", with the reason | reconnecting in the UI |
| Steam Web API down | linking degrades; bans read "unknown" | itself — unknown is never treated as clean |
| No qualifying match in the window | a full refund, zero rake | — you cannot lose by not playing |

## Before merging

- [ ] `STEAM_OPENID_REALM` and `STEAM_OPENID_RETURN_URL` set to the Vercel domain
- [ ] `WEB_ORIGIN` set to the Vercel domain
- [ ] `GC_SHARED_SECRET` and `STEAM_API_KEY` in the `moneymatch-shared` group
- [ ] `GC_REFRESH_TOKEN` set on `moneymatch-gc`, from an account that owns CS2 and that nobody plays on
- [ ] `VALVE_CHAIN_ENABLED=true` — the paste box is gone, so collection is the only ingest path
- [ ] `DEMO_LOGIN_ENABLED`, `DEMO_SIMULATE_ENABLED` and `E2E_AUTH_ENABLED` left unset
- [ ] No `cs2.faceit` contest in flight, or `0022` refuses and the deploy fails
- [ ] `VITE_API_BASE_URL` on Vercel pointing at the Render API
