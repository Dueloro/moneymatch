# Money Match — Implementation Status

**Written 2026-08-17.** An honest, detailed account of what the code actually does today:
the mathematics, the matchmaking algorithms, how money moves, and how the demo differs from
production.

**How this was compiled:** by reading the source on `main` (commit `ede7ce6`, the
`feat/csgo_testing` merge), dumping the live route table from the FastAPI app, running the
bar-placement code directly against real data, and probing the deployed API at
`moneymatch.onrender.com`. Where something is claimed but unverified, it says so. Where the
code disagrees with its own documentation, §16 records it.

**Legend:**

| Mark | Meaning |
| --- | --- |
| ✅ | Implemented and verified working |
| 🟡 | Implemented, not verified end to end in production |
| ⚠️ | Implemented but currently broken or degraded |
| 🔌 | Deliberately inert — the seam exists, the real thing does not |
| ❌ | Not built |

---

## 1. The honest summary

Money Match is a **play-money** skill-wagering platform. A player links a game account, joins
a contest, plays a real match on the real game, and the platform grades the result from the
game's own data and moves money between players' wallets minus a rake.

Everything in that sentence is really implemented — ledger, escrow, grading, settlement, rake
and payouts all run for real, with integer-cent arithmetic and enforced reconciliation
invariants. **The only fake part is the currency.** Every wallet is created with
`currency="DEMO"`; there is no payment processor, no deposits, no withdrawals, and no KYC
enforcement anywhere in the codebase.

---

## 2. Deployment topology

| Component | Where | Status |
| --- | --- | --- |
| Web app (React + Vite) | Vercel — `moneymatch-beta.vercel.app` | ✅ |
| API (FastAPI) | Render — `moneymatch.onrender.com` | ✅ |
| Postgres | Render managed | ✅ |
| Settlement worker | In-process in the API (`RUN_WORKER_IN_PROCESS=true`) | ✅ |
| GC sidecar (Node) | Render private service `moneymatch-gc` | ⚠️ reachable, `ready:false` |
| Auth | Supabase (HS256 secret or JWKS) | ✅ |

Migrations run from the Docker `ENTRYPOINT` (`alembic upgrade head`) before the app binds, so
a deploy cannot serve a stale schema. **24 migrations**, head `0024_retire_cs2_faceit`.

---

## 3. Data model

- **Identity** — `users` (auth_id, username, friend_code, residence_state, dob attestation,
  role, status, active_games), `linked_accounts` (one host account per game, soft-unbind,
  profile snapshot, `models_bootstrapped_at`)
- **Money** — `wallets`, `ledger_entries` (immutable, append-only), `platform_ledger_entries`
  (rake), `limits`
- **Contests** — `matches` + `match_players`, `solo_pools` + entries, `tournaments` + entries,
  `queue_tickets`
- **Skill** — `metric_models` (user × game × metric: μ, σ, n)
- **CS2** — `cs2_matches` (`share_code` uniquely indexed), `cs2_share_chains` (one cursor/user)
- **Ops/risk** — `feature_flags`, `risk_flags`, `admin_audit`, `disputes`, `raw_payloads`
- **Social** — friendships, conversations, messages, notifications, push subscriptions
- **Demo** — `simulated_matches`

---

## 4. Games and adapters

Every game implements one `GameAdapter` interface behind a registry. **The contest engines
never know which game they are grading.**

| Game | Adapter | Source | Markets | Status |
| --- | --- | --- | --- | --- |
| Counter-Strike 2 | `cs2_steam.py` | Steam OpenID + share codes + Game Coordinator | `cs2_kd_ratio`, `cs2_headshot_pct`, `cs2_kills` | 🟡 |
| Chess | `chess_lichess.py` | Lichess API | `chess_moves`, `chess_accuracy`, aggregates | ✅ |
| Dota 2 | `dota2_opendota.py` | OpenDota | `dota2_kda_ratio`, `dota2_gpm` | ✅ |
| PUBG | `pubg.py` | Official PUBG API (throttled 9/min) | `pubg_kills`, `pubg_damage`, `pubg_headshot_pct` | ✅ |
| Simulated | `simulated.py` | Injected results | wraps any game | 🔌 |

`cs2.faceit` was retired in migration `0024`, which **refuses to run** if any FACEIT contest is
still in flight — the alternative is stranding entries in escrow.

**No CS2 ADR market**, deliberately: ADR needs a parsed demo file, and the GC scoreboard only
carries kills, deaths, assists, headshots, MVPs and team scores. A market that cannot be
graded would take money for a wager that could never settle.

Per-game history floors (`GAME_HISTORY_FLOOR`) gate head-to-head *stat duels*: chess 20 rated
games, Dota 25, PUBG 20, **CS2 0** (a Steam user starts with no history here, so the prior
covers it instead).

---

## 5. The mathematics

All of this is pure, I/O-free and unit-testable. Every number a player sees is derived from
stored inputs and **re-derives byte-for-byte** from the saved snapshot — that is the audit
replay guarantee. No API surface accepts a bar, a room bar, or a payout.

### 5.1 Metric models — recency-weighted EWMA

`metric_models_service.compute_ewma(values, half_life=10)` over chronological values:

```
wᵢ = 0.5 ^ ((n − 1 − i) / 10)          # newest sample weight 1, halving every 10
μ  = Σ wᵢxᵢ / Σ wᵢ
σ  = sqrt( Σ wᵢ(xᵢ − μ)² / Σ wᵢ )
n  = len(values)                        # raw count, drives provisional-ness
```

`n` is the **raw** sample count, not the effective weighted count. Bootstrap pulls up to 50
recent finished matches through the adapter.

### 5.2 The prior and shrinkage

`skill_prior.shrink(μ, σ, n, prior, weight=10)` blends a player's own record toward a
population expectation:

```
μ_blended = (n·μ + w·μ_prior) / (n + w)
σ_blended = sqrt( (n·σ² + w·σ²_prior) / (n + w) )      # blended in VARIANCE, not σ
```

At n=10 your record and the prior weigh equally; by n=40 you are 80% yourself. Variance-space
blending is deliberate — averaging variances keeps the units honest.

The prior itself was **empirically fitted**, and this is the most rigorous piece of modelling
in the codebase. Sampled 2026-08-09 from eight finished Lichess arena tournaments, standard
chess only: **4,647 games, 4,526 decisive** after excluding draws (2.6%).

```
rating band      n    mean moves    sd
1000           158       25.5      11.7
1200           273       29.4      11.8
1400           673       32.0      12.0
1600          1107       32.3      11.5
1800          1318       34.4      11.7
2000           698       37.7      12.5
2200           248       39.1      13.4
```

Two findings: mean length rises near-linearly with rating (~1 move per 100 Elo), while the
spread is flat near 12 moves in every band. Hence
`mean_moves(elo) = 16.65 + 0.01013·elo`, σ = 11.94, held flat outside 800–2600.

> **⚠️ Honest limitation — shrinkage is a no-op outside chess.** `_PRIORS` is an **empty
> dict**, and `prior_for()` returns a value only for `chess_moves`. For every CS2, PUBG and
> Dota metric it returns `None`, and `shrink()` with `prior=None` returns `(μ, σ)`
> **unchanged**. So the "blend toward what your rating predicts" behaviour applies to chess
> only. `host_rating()` compounds this: it reads `formats` / `primary_speed` from the profile
> snapshot, which is a chess-shaped structure, so it returns `None` for CS2 regardless.

### 5.3 Effective sigma — the spread floor

```
effective_sigma(σ, increment) = max(σ, 2 · increment)
```

A bar quoted in whole units cannot express difficulty at sub-unit resolution; with a tight
spread all three difficulties round to the same number and you get one card printed three
times. Two increments of spread guarantees the easy→medium gap (0.457σ) survives rounding.

Critically, this is applied **once**, where the model is read, and used for the bar, the fair
band and the disclosed clear rate alike. Flooring only at bar placement previously made the
bar and the fairness check disagree, so tight-spread players could never form a room.

`METRIC_BAR_INCREMENT`: `cs2_kd_ratio` 0.05, `cs2_headshot_pct` 1.0, `cs2_kills` 1.0,
`chess_moves` 1.0, `dota2_kda_ratio` 0.1, `dota2_gpm` 10.0.

### 5.4 Personal bar placement

```
bar = max(floor, round_to_increment( μ + k·σ ))          # higher-is-better
bar = max(floor, round_to_increment( μ − k·σ ))          # lower-is-better (chess_moves)
```

with `k` from the difficulty (`POOL_DIFFICULTY_K`):

| Difficulty | k | Implied clear rate `1 − Φ(k)` |
| --- | --- | --- |
| Easy | 0.385 | ~35% |
| Medium | 0.842 | ~20% |
| Hard | 1.282 | ~10% |

**Lognormal branch.** For metrics in `METRIC_POSITIVE_SUPPORT` the bar is placed on a
lognormal instead:

```
s² = ln(1 + σ²/μ²)
m  = ln(μ) − s²/2
bar = exp(m ± k·s)
```

This exists because on a normal, `μ − k·σ` walks off the end of the scale as the spread
approaches the mean — which is how a hard chess pool once asked for **minus six moves**.
Measured against the 4,647-game sample the lognormal was accurate to 1.26 moves versus the
normal's 1.44, and where the normal predicted a 4%-clear bar of 3.4 moves for a 1000-rated
player, the true figure was 7.

> **`METRIC_POSITIVE_SUPPORT` currently contains `chess_moves` only.** All three CS2 metrics
> are placed on a **normal** — including headshot %, which is a bounded proportion whose
> variance depends on the kill count, and kills, which is an overdispersed count. This is a
> modelling simplification, not a considered choice for those metrics.

**Worked example (verified by running the real code).** A freshly linked CS2 player whose
Steam game details are private gets the default prior μ = 1.00, σ = 0.25 for K/D:

```
easy   1.00 + 0.385·0.25 = 1.0963 → round to 0.05 → 1.10
medium 1.00 + 0.842·0.25 = 1.2105 → 1.20
hard   1.00 + 1.282·0.25 = 1.3205 → 1.30
```

With **public** stats for a real account (lifetime K/D 0.606), the seeded μ becomes 0.606 and
the same arithmetic yields 0.70 / 0.80 / 0.95. Kills (μ 10.92, σ 6) yields 13 / 16 / 19, and
headshot % (μ 42.34, σ 12) yields 47 / 52 / 58. These match the deployed app exactly.

### 5.5 Clear probability (the disclosed difficulty)

```
z = (bar − μ)/σ                       # or (ln(bar) − m)/s on the lognormal
p = 1 − Φ(z)                          # higher-is-better
p = Φ(z)                              # lower-is-better
```

`positive` must be passed identically to `personal_bar` and `clear_prob` — placing a bar under
one distribution and judging it under another is not a rounding difference, it is two
different answers to the same question. The percentage on the card ("34% of your recent
matches clear it") is computed from the bar actually quoted and the same (μ, σ) used to place
it, so the card and settlement agree by construction.

**It is a model output, not a measured frequency. Nothing in the codebase compares predicted
clear rates against realised ones.** There is no calibration harness. ❌

### 5.6 Room bar and composition

```
room_bar = round_to_increment( mean(personal_bars) )
p_target = 1 − Φ(k)
band     = [ p_target/2 , min(2·p_target, 0.5) ]
```

A room forms **only if every member's implied clear probability against the shared room bar**
sits inside that band:

```
pᵢ = 1 − Φ((room_bar − μᵢ)/σᵢ)   ∈ band     for all i
```

This is the anti-shark rule in both directions: a strong player cannot drag the average down
to trivial-for-them, and a weak outlier cannot be dragged up to impossible.

Plus a **personal-bar spread cap**:

```
σ_pooled = sqrt( Σσᵢ² / N )                      # RMS
max(bars) − min(bars) ≤ 1.5 · σ_pooled           # POOL_BAR_SPREAD_CAP_SIGMA
```

### 5.7 Tournament dispersion and scoring

```
max(μ) − min(μ) ≤ 1.0 · σ_pooled                 # TOURNAMENT_DISPERSION_CAP
score = mean of the FIRST N qualifying matches   # TOURNAMENT_SCORE_N = 3
```

**First-N, not best-of** — extra games buy zero extra chances. An entrant with no qualifying
match ranks last.

Field size 10, minimum 6, minimum 4 ranked finishers, 48-hour window, prize weights
**50 / 30 / 20**.

### 5.8 Money math — exact integer cents

No floats anywhere in the money path. The load-bearing rule: **`sum(payouts) + rake == pot`**,
asserted in `Split.__post_init__`, so a non-reconciling split cannot be constructed.

```
rake        = pot · rake_bps // 10_000           # FLOOR, so rake ≤ true percentage
distributable = pot − rake
each        = distributable // num_winners
remainder   = distributable − each · num_winners
rake       += remainder                          # leftovers go to rake, never minted or lost
```

Default rake **1000 bps = 10%**. Weighted splits (tournaments) floor each place's share by
weight with the remainder landing in rake; tied places are re-divided by the tournament engine
itself, with the tie remainder going to the **earlier enqueue** rather than the rake, so the
invariant still holds exactly.

**Display multipliers** are computed, never configured:

```
h2h_multiplier   = 2·(1 − rake)                  # ×1.80 at 10%
pool_multiplier  = min( (1 − rake)/p_target , room_size·(1 − rake) )
```

The pool cap matters: a pool is peer-funded, so the most anyone can take home is every entry
less rake. Without the cap a low clear rate divides by a vanishing number — a 0.04% tier once
quoted 22,500× and advertised **$225,000 on a $25 entry**, which the pool could never fund.

---

## 6. Matchmaking algorithms

### 6.1 Solo pools — queue, then form

Pools are **queue-matched only**. There is no browse-and-join surface; `/pools/open` is not a
route.

**Enqueue** (`pool_engine.enqueue`), in order:

1. Geo-fence (`assert_can_enter`) — **before anything else**, so a blocked resident never gets
   a ledger row
2. Game enabled flag, `queue_paused` kill switch
3. Provisional check: `n < STAT_BASELINE_MIN_N` (=1) → refused
4. Sandbagging flag check → refused if flagged
5. Staking limits (balance, trailing-24h loss/entry caps, concurrency cap)
6. **Freeze the baseline** into `baseline_snapshot` on the ticket and compute
   `personal_bar = round(μ + k·σ)`
7. **No escrow while waiting** — a waiting ticket holds no money

**Room formation** — match-on-write with `FOR UPDATE SKIP LOCKED`:

1. Gather compatible waiting tickets in the same bucket (game × metric × difficulty × entry)
2. Derive `room_bar` from the mean of members' frozen personal bars
3. Check `composition_ok` for **every** member (the band in §5.6) plus the spread cap
4. Check `can_pair` for **all pairs** in the room (anti-collusion — §9)
5. Only then: escrow the whole group atomically, lock the room, start the 24-hour window

Full room `POOL_ROOM_SIZE = 4`; at the end of the widening ladder it will form down to
`POOL_MIN_ROOM = 3`. Tickets past `QUEUE_TICKET_TTL_SECONDS` are expired by the worker (no
escrow was held, so nothing to refund).

### 6.2 Head-to-head — duel forecast pairing

Because equal stakes forbid handicaps, **the only lever for fairness is who plays whom**.

**Stat duels.** Each player's next match is modelled as an independent normal:

```
P(a beats b) = Φ( (μa − μb) / sqrt(σa² + σb²) )
```

A pair is *eligible* only if that probability sits inside `[0.5 − w, 0.5 + w]`.

**The widening ladder** (`PAIRING_WIDENING_LADDER`) — `w` grows with the older ticket's age:

| Waiting | w | Fair window |
| --- | --- | --- |
| ≤ 30s | 0.05 | 45% – 55% |
| ≤ 120s | 0.10 | 40% – 60% |
| ≤ 300s | 0.15 | 35% – 65% |

Two tickets pair within the **wider** of their two ladders. Past the last stage the math stops
auto-widening and the UI offers keep-waiting / cancel-refund.

**Chess** uses an Elo band instead, because Elo already *is* the forecast: band starts at 100,
widens 12 Elo/second, capped at 800.

**Selection among eligible candidates** — lowest composite score wins:

```
score = 0.60·|μa − μb|/σ_pooled  +  0.30·|ratingA − ratingB|/400  +  0.10·|σa − σb|/σ_pooled
```

The variance term is deliberate: it avoids pairing a steady player against a boom-or-bust one,
which would be "fair" on means while being a coin-flip in practice.

**`can_pair` is the single anti-collusion chokepoint** and rejects: self-pair, same host
account, a re-pair within `REPAIR_COOLDOWN_SECONDS` (24h), and provisional metrics.

**Escrow happens at confirm**, not at enqueue. Both sides confirm within
`MATCH_CONFIRM_TTL_SECONDS` (24h); a no-show cancels and refunds with zero rake.

### 6.3 Tournaments

Field of 10 (min 6), formed under the μ-dispersion cap, 48-hour window, scored on the
first-3 mean, paid 50/30/20 among ranked finishers (min 4 ranked).

### 6.4 Concurrency and race-safety

Every claim uses `FOR UPDATE SKIP LOCKED`. Two concurrent enqueues racing for one waiting
ticket produce exactly one match — the loser simply keeps waiting. Each unit of settlement
work runs in **its own transaction**, so a crash between claim and settle leaves the row
re-claimable. Multiple worker copies cannot double-settle.

---

## 7. Grading and settlement

**Grading** (`grading.py`) is server-authoritative with **zero self-reporting** — every input
comes from a host API through an adapter, and the normalised evidence is persisted to
`raw_payloads` and referenced from the settlement.

| Market | Rule |
| --- | --- |
| `win_h2h` (chess) | the brokered game's result between the two bound accounts; draw → PUSH |
| `win_next` (CS2/Dota) | each player's first finished match after `matched_at`; both-win or both-lose → PUSH |
| stat races | each player's rate stat from that first finished match; higher wins; equal → PUSH |

**The settlement worker loop**, each cycle:

1. Due matches (ACTIVE / AWAITING_RESULT) → grade → settle; **or extend the window on a host
   outage; or CANCEL + refund at the hard ceiling**
2. PENDING matches past their confirm window → cancel + refund whoever escrowed
3. Waiting tickets past TTL → expire
4. Kill switches: `settlement_paused` halts the loop (fail closed); `queue_paused` drains the
   queue into clean cancels

**A post-settle reconciliation breach raises `ReconciliationError`, sets `settlement_paused`
and stops the worker — money never commits against a broken book.**

The worker writes a heartbeat flag each cycle; `/health` and the admin reconciliation view
redden when it goes stale (120s). A heavier nightly pass refreshes metric models and runs the
derived risk detectors.

**Watchdog rules:** a host outage returns `pending` so the window is extended rather than
consumed; a one-sided stat duel becomes a **forfeit win** only after the full window plus a
disclosed grace period; nothing resolvable at the deadline → CANCEL + refund.

**No qualifying match ⇒ full refund, zero rake.** You cannot lose by not playing.

---

## 8. The CS2 verification pipeline

The most novel part of the system. **The insight it rests on: you do not need to parse a demo
file to settle a wager** — when the GC resolves a share code, the reply already contains the
final scoreboard.

1. **Steam OpenID 2.0** (`steam_openid.py`). Security rests on one step: the callback's
   parameters are sent **back to Steam** for verification. Reading the SteamID out of
   `claimed_id` without that round trip would let anyone sign in as anyone. ✅
2. **Share-code codec** (`sharecode.py`) — base-57 over 144 bits, little-endian into
   `match_id` (u64), `outcome_id` (u64), `token_id` (u16). Encoding is implemented purely so
   the codec can be round-trip tested: a decoder that drifts does not fail loudly, it grades
   the wrong match. ✅
3. **GC sidecar** (Node) — the Game Coordinator speaks protobuf over the Steam network and has
   no maintained Python client. One request in flight, ~1.2s apart, loopback-only,
   shared-secret protected, supervised. ⚠️
4. **GC client** — timeout plus a **circuit breaker**: three consecutive failures stops calls
   for 30 seconds. ✅
5. **Intake checks** (`cs2_submission.py`) — the code must decode; your SteamID64 must be in
   the roster; the match must post-date the wager; the code must not already be recorded
   (**unique index on `share_code`** — the only place the "one match settles one wager" rule
   cannot be raced). Plus a round floor: 16 for Premier/Competitive, 9 for Wingman, below
   which the match was surrendered or abandoned. ✅
6. **Automatic collection** (`cs2_chain.py`) — Valve stores matches as a linked list, so
   `GetNextMatchSharingCode` turns one code into the next forever. Only a cursor persists.

   | Code | Meaning | Behaviour |
   | --- | --- | --- |
   | 200 | newer match exists | resolve, store, advance cursor |
   | 202 | caught up | **normal**, the common case |
   | 412 | cursor not this player's | stop and re-prompt; retrying can never work |
   | 403 | auth code rejected | chain marked broken until reconnected |
   | 429/5xx | rate limited / down | back off, cursor untouched, chain stays healthy |

   Getting permanent failures wrong matters beyond one user: Valve temporarily blocks an API
   key that keeps presenting bad auth codes. A walk is capped at `MAX_CODES_PER_SYNC`, and the
   sync runs **before** pools settle. 🟡
7. **The adapter** — once stored, a match is ordinary match history. **Intake is the only
   CS2-specific step in the entire system.**

**Why this is a real integrity story:** matches are pulled from Valve's own linked list, so a
player **cannot cherry-pick which match counts**. Casual, Deathmatch and Arms Race produce no
share code at all, so mode filtering is free — if a code resolves, it was real matchmaking.

**What has never happened:** no CS2 match has ever been collected in production.
`last_code_at` is `null`. The one assumption round-trip testing cannot cover — that a decoded
`match_id` is one Valve recognises — remains unverified against a real code.

---

## 9. Risk, fairness and compliance

| Control | Implementation | Status |
| --- | --- | --- |
| **Sandbagging** | z-test of recent-form mean against the player's own older baseline; writes a `risk_flags` row and **blocks metric wagers** on that game/metric until an admin clears it. Host outage during evaluation fails open; persisted flags still block | ✅ |
| **Anti-collusion (pairing)** | `can_pair` — self-pair, same-host, 24h re-pair, provisional metrics | ✅ |
| **Anti-collusion (caps)** | 3 rake-bearing contests/day, 10/week per pair. Past the cap a challenge becomes a **zero-rake friendly** rather than being blocked | ✅ |
| **Derived detectors** | Nightly pass over settled history: `win_streak`, `pair_cap`. Informational, never blocking | ✅ |
| **Geo-fence** | Enforced **before any escrow**. 14 states seeded in migration 0001 into the admin-editable `geo_config` flag: **AZ, AR, CT, DE, FL, IN, LA, MD, MN, MT, SC, SD, TN, WY** | ✅ |
| **Staking limits** | Entry band $1–$100; trailing-24h loss $200 / entry $500 / deposit $1,000; max 3 concurrent contests. Read from the immutable ledger so they cannot be spoofed. Raising a cap is delayed 24h; lowering is instant | ✅ |
| **Self-exclusion** | `POST /me/self-exclude` | ✅ |
| **Age / residence gate** | `assert_can_enter` raises on a null residence state — a real user cannot stake before onboarding | ✅ |
| **Reconciliation** | Per-contest `entries == distributed + rake + still_held`; global `sum(available + escrow) == promo funding − rake`. **Fail-closed** | ✅ |
| **Chess farming guard** | `RATED_ONLY_GAMES` — chess settles from rated games only | ✅ |
| **Resign exploit guard** | `chess_moves` only counts matches you **won**; otherwise resigning on move one scores 1 and clears every hard pool | ✅ |
| **KYC** | `kyc_live` flag, `kyc_status` column, $500 cumulative-entry policy hook | 🔌 inert |
| **Payments** | `payments_live` flag | 🔌 inert |

Both `payments_live` and `kyc_live` are guarded in code: turning either on with no live
provider compiled in **raises at the resolver**, so a config flip alone can never move real
money.

---

## 10. Social, notifications, admin

- **Social** — friends (request/accept/decline/block), friend codes, DM chat with invite
  cards, support thread, presence heartbeat
- **Notifications** — in-app, Web Push (VAPID; no-op without a keypair), email via Resend
  (no-op without a key; synthetic `@users.moneymatch.app` addresses are never emailed)
- **Live** — SSE at `/events/stream` with a ticket handshake; live snapshots refresh every 30s
  for in-flight contests, standings every 10 min
- **Leaderboard** — ROI over a rolling 30 days, min 3 settled rake-bearing contests, practice
  opponents excluded
- **Admin** — users (freeze/unfreeze/adjust), contests, queue, disputes, risk queue, ledger,
  reconciliation, feature flags. **Every admin write lands an `admin_audit` row**; flag flips
  take effect per-request with no restart
- **Disputes** — polymorphic across contest types, player-raised, admin-resolved, with
  `resettle` and `void`

---

## 11. Demo vs production — the three columns

This is the section most worth reading carefully, because "demo", "production as designed" and
"production as currently running" are three different things.

### 11.1 Feature-by-feature

| | Demo account | Production as designed | Production **as it runs today** |
| --- | --- | --- | --- |
| Sign-in | `POST /demo/login`, no password, shared user | Supabase (Google / email+password) | ✅ works |
| Onboarding | pre-set state + 18+ attestation | user must supply both before staking | ✅ enforced |
| Opponents | practice bots fill the room | other real players only | ⚠️ no liquidity — real users queue without matching |
| Room formation | immediate | needs 3–4 real entrants in the same bucket | ⚠️ effectively never |
| CS2 identity | real Steam OpenID | identical | ✅ works |
| Match collection | real GC + real chain | identical | ⚠️ never collected a match |
| Grading / escrow / rake / settlement | identical | identical | ✅ code path proven |
| Currency | DEMO | **DEMO** | play money |
| Deposits / withdrawals | `demo-deposit` / `demo-withdrawal` | ❌ not built | ❌ |
| KYC | none | 🔌 inert | 🔌 |

### 11.2 How the practice opponents actually work

`test_opponents.py` is explicitly labelled scaffolding — *"Delete it before launch. Everything
fake in the product lives here and in the three router call sites that reference it."*

- Opponents are **ordinary users** created through the same provisioning as anyone else, then
  enqueued through the engines' own public `enqueue()`. **No engine has a special case for
  them**, so what you exercise is the real path.
- Their baselines **mirror yours exactly** (`_MU_FACTOR = 1.0`). Giving them deliberately bad
  stats is tempting but self-defeating: the composition predicate would reject the room and
  you would learn nothing.
- They **never play**. At settlement they are graded as having missed their bar
  (`graded_as_failed`), which is what makes your stake real — clearing your bar pays out of
  *their entries*. They are the only entrants ever graded without being looked up; a real
  player who produces no qualifying game is **unverifiable and refunded instead**.
- **One of them clears.** `CLEARING_HANDLES = {testbot_ada}` exists because a room where every
  bot misses has only one possible outcome, so the rule that actually governs a pool —
  clearers *split* the pot — was never reachable with one real player.
- Their daily loss caps are raised to $1M **as data, not as a code exemption**, so nothing in
  the money path grows a branch that could ever apply to a real account. This was a real bug:
  the bots built to miss lost their entry every room, accumulated genuine daily losses, and
  were eventually refused by the responsible-gaming cap.
- They are excluded from the leaderboard and the live activity ticker.
- `is_enabled()` keys off **who is playing** (`demo_mode.is_demo_user`), not an environment
  flag. **A real signup never sees a fabricated opponent in any environment.**
- `purge()` deletes every one of them in a single call; wallets, tickets and entries cascade.

### 11.3 Where demo-pool money comes from

Practice opponents hold **real wallets and their entries genuinely fund the pot**. From a
settled four-handed room:

```
demo           escrow_hold      -2500   escrow +2500
demo           escrow_release       0   escrow -2500
testbot_ada    escrow_hold      -2500   escrow +2500
testbot_ada    escrow_release       0   escrow -2500
testbot_ada    payout           +9000
testbot_bo     escrow_hold      -2500   escrow +2500
testbot_bo     escrow_release       0   escrow -2500
testbot_cy     escrow_hold      -2500   escrow +2500
testbot_cy     escrow_release       0   escrow -2500

sum of every amount: -1000   <- the rake, and nothing else
```

Four $25 entries held and deducted; the clearer paid $90 (pot less 10% rake). The ledger sums
to exactly the rake, so money is conserved and none is minted. **The only fabricated thing
about an opponent is its result, never its balance.** That is already the production
behaviour — deleting `test_opponents.py` changes no money code; the bots simply stop existing
and real losers fund the pot instead.

### 11.4 The demo escape hatch 🔌

`POST /demo/simulate_result` injects a finished match; `POST /demo/force_settle` settles a
contest immediately (a tournament otherwise waits 48 hours). Both **admin-only *and* behind
`DEMO_SIMULATE_ENABLED`**, which defaults off.

The property that makes them honest: an injected result enters at the **same seam** a real one
does — `registry.get(game).poll_eligible_games()` — so there is no `if simulated` branch in
grading, the engines, or the payout path. The moment there were one, a green demo would stop
being evidence that the real path works.

Also present: `POST /demo/reset` and `POST /demo/relink` (swap the demo's placeholder handles
for a real account per game).

### 11.5 What is off in production, and stays off

Verified by building the app with a production environment and reading the route table:

- `/api/v1/demo/*` is **not mounted** (`DEMO_LOGIN_ENABLED` defaults false)
- `/api/v1/dev/e2e/token` is **not mounted** — double-gated on `E2E_AUTH_ENABLED` *and*
  `env != prod`, with the handler re-checking both
- Injected results impossible — with `DEMO_SIMULATE_ENABLED` off the adapter wrapper is never
  constructed
- Practice opponents cannot appear — keyed off the demo account, not an env flag

`/api/v1/wallet/demo-deposit` **is** mounted in production. That is consistent only because
every wallet is play money, and it is the first thing that must change when that stops being
true.

### 11.6 The gap that matters

**Room formation.** A pool needs 3–4 entrants in the same game × metric × difficulty × entry
bucket. With 4 games × 3 metrics × 3 difficulties × 3 entry tiers that is ~108 buckets. The
demo hides this with bots; production does not. Until there is concurrent traffic, real users
will queue without matching. **That is a liquidity problem, not a bug, and it is the entire
reason the scaffolding exists.**

---

## 12. User flows

### Real signup

1. Sign in through Supabase
2. **The account row is created on the first authed call** — `get_or_create_user` inserts the
   user, provisions a wallet, posts the signup grant, and handles two races (duplicate
   `auth_id` returns the winner; `friend_code` collision retries). Nothing needs configuring in
   Supabase beyond auth itself
3. `needs_onboarding` routes to `/signin`, which collects username, residence state and the
   18+ attestation; `PATCH /me` records them. **No staking until both exist**
4. Link a game account (`POST /links`, or Steam OpenID for CS2)
5. CS2 only — three one-time steps that **cannot be done for them**: Steam sign-in, create a
   **match authentication code** (issued per Steam account; no bulk or delegated form), and
   name one match as the starting cursor
6. Join a contest → escrow → play a real match → worker collects and grades → settlement pays
   out and posts rake

### CS2 collection, once set up

`worker cycle → chain sync → GetNextMatchSharingCode → 200? → GC resolve → store cs2_match →
adapter surfaces it as ordinary history → pool grades at window close`

---

## 13. What is NOT implemented

- ❌ **Real money.** No processor, deposits, withdrawals or payouts. Every wallet is `DEMO`.
- ❌ **KYC enforcement.** Flag, column and policy hook exist; nothing verifies an identity.
- ❌ **CS2 ADR, KAST, opening duels, clutches** — all need demo-file parsing.
- ❌ **Demo download and parsing.** Tickets only.
- ❌ **Calibration measurement.** Nothing compares predicted clear rates to realised ones.
- ❌ **Non-chess priors.** `_PRIORS` is empty; shrinkage is inert outside chess.
- ❌ **Licensing position.** No state-by-state legal opinion; the excluded-state list is
  inherited from a proof-of-concept, not from counsel.
- ❌ **Sidecar redundancy.** One Node process, one Steam account — also a ToS exposure, since
  an automated Steam login that gets banned stops all CS2 settlement.
- ❌ **Alerting.** A stalled sidecar or a chain collecting nothing is invisible without
  manually querying an endpoint.
- ❌ **Mode separation for CS2.** Premier / Competitive / Wingman appear to share one model.

---

## 14. Known issues as of 2026-08-17

1. ⚠️ **Deployed GC sidecar reports `ready:false`** and has for three days. The response is
   **ambiguous by design**: `gc_client.health()` never raises and returns the same shape
   whether the sidecar is up-but-unattached or entirely unreachable; the router discards the
   `detail` field that would distinguish them.
2. ⚠️ **No CS2 match has ever been collected.** `last_code_at` is `null` in production.
3. ⚠️ **Refreshing a linked CS2 account wipes the seeded prior.** Only the Steam OpenID
   callback calls `cs2_prior.seed()` (n=3). Both `linking_service.bind()` and
   `linking_service.refresh()` call `metric_models_service.bootstrap()`, which rebuilds from
   *stored* matches — of which there are zero — writing n=0. The metric then reads provisional
   and Solo Pools shows "No pools on this game yet." Reproduced locally in a rolled-back
   transaction; matches deployed behaviour exactly.
4. ⚠️ **The CS2 prior ignores data it already has.** `_derived(kd)` scales generic HS%/kills
   defaults by the K/D ratio instead of using `total_kills_headshot` and
   `total_matches_played`, which Steam returns in the same response. For a real test account
   (K/D 0.606, HS% 36.6, 8.19 kills/match) it seeds HS% 42.3 and kills 10.9, quoting easy bars
   of 47 and 13 — both well above the player's actual form.
5. 🟡 **`GetUserStatsForGame` returns 400 unless Steam *Game details* are public.** This is the
   normal path, not the edge case, so most users get the default prior.
6. 🟡 **Wingman and Premier likely share one `cs2_kills` model.** Wingman is 2v2 first-to-9,
   Premier 5v5 first-to-13; kills are not the same random variable. Unverified.
7. 🟡 **`uvicorn --reload` wedges locally** — accepts TCP but never answers. Run without it.

---

## 15. Documentation discrepancies found while writing this

Recorded because they mislead anyone reading the source.

1. **`fairness.py`'s module docstring is stale.** It states `k = {easy: 0.5, medium: 1.0,
   hard: 1.75}` with clear rates ≈31/16/4%. The code reads `POOL_DIFFICULTY_K` from
   `constants.py`, which is `{0.385, 0.842, 1.282}` → 35/20/10%. Verified by running the code:
   observed bars match the constants, not the docstring.
2. **`METRIC_BAR_INCREMENT` still contains `cs2_adr`**, a market retired in migration 0024.
3. **`skill_prior`'s module docstring describes shrinkage as a general mechanism**; `_PRIORS`
   is empty, so it applies to `chess_moves` alone.
4. **`docs/game/cs2-steam.md` says the GC sidecar "is not in the repo."** It is —
   `gc-sidecar/` with `server.js`, `supervise.js`, `get-token.js` and a Dockerfile, all
   tracked.

---

## 16. Test and verification status

- **API:** 93 test files, 657 test functions (parametrisation expands this — project docs
  report 1,028 collected — **this was wrong; the measured figure is 1052**, recorded in
  `OPEN_QUESTIONS.md`). **The suite was not re-run while writing this document.**
- **Web:** 30 vitest files, 4 Playwright e2e specs.
- **CI:** `alembic check` runs in CI, so a model/migration mismatch fails the build.
- **Verified by direct probing this week:** all 24 migrations applied and at head; a
  production-configured app mounts neither `/demo/*` nor the e2e token minter; `ENV=prod`
  refuses to boot with a localhost origin; CORS is restricted to the Vercel domain; the local
  GC sidecar attaches to Valve and correctly answers `match_not_found` for a synthetic share
  code; bar placement reproduces the deployed numbers exactly.

---

## 17. Where the defensibility actually is

Anyone can build a wallet and a pot. The hard, non-obvious part of this codebase is
**trustworthy per-match verification without cooperation from the game publisher**: the
share-code codec, the protobuf bridge, automatic chain walking, roster verification, replay
prevention via a unique index, and round floors that reject forfeits. That machinery
generalises across titles, and the contest engines behind it are entirely game-agnostic.

The second, quieter asset is the **money layer**: integer-cent arithmetic, an append-only
ledger, enforced per-contest and global reconciliation, and a worker that halts rather than
commit against a broken book.

The main risks to the first are external — Valve could deprecate or break the sharing API or
the GC interface, and the sidecar's automated Steam account is both a terms-of-service
exposure and a single point of failure.
