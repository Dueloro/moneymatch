# Money Match — Bucketing System: Phased Implementation Plan

A production build plan for the one-bar-per-bucket ranking & matchmaking system.
Each phase ends with a **test gate** you must pass before the next phase starts, so
the system is provably correct at every step — not just at the end.

This plan is grounded in the real codebase (`apps/api/src/moneymatch_api/…`) and the
metrics/floors already defined in `constants.py`. It **adds** the bucketing layer to
what exists; it does not rewrite the adapters or the market/settlement kinds.

---

## How to read this document

Every phase has the same shape:

- **Goal** — one plain sentence.
- **Why** — what breaks if we skip it.
- **Build** — the concrete tables and code, with the module they live in.
- **Test gate** — the checks that must be green to move on. A phase is **not done**
  until every box is ticked.

The phases are in dependency order. You can demo after Phase 5 (a real wager settles
end to end) and beta-launch after Phase 6 (disputes + audit are the trust layer).

---

## Ground rules (non-negotiable, apply to every phase)

These carry over from the earlier briefs and must hold throughout:

1. **Branch discipline.** All work on `fixes/testing`. Never `main`, never force-push,
   never rebase pushed history.
2. **Never touch production directly.** No manual migrations against the deployed DB,
   no live flag flips, no mutating calls to the deployed API. Ship via migrations +
   feature flags that default **off**.
3. **The money invariant is sacred.** For every settled contest,
   `sum(payouts) + rake == pot`, to the cent. This is asserted in code before a
   settlement commits, and tested in Phase 5.
4. **Fail closed.** If a result can't be verified, a number looks impossible, or a feed
   is down → **void and refund**, never guess.
5. **Tests run migrations, not `create_all`.** The test fixture must build the schema by
   running the real migration chain, so seed data and constraints are actually exercised.
   (This closes the seed-drift gap that let the geo-fence bug reach production.)
6. **One logical change per commit; full suite green per commit.**

---

## Launch scope — games, modes & metrics (the single source of truth)

This table is authoritative. Every phase references it: it decides which modes reach
settlement, which metrics get a bucketed market, and which placement system a game uses.
"Store" and "rate/settle on" are **different** — we always store every field for the future
ranking model (Phase 1), but we only build buckets and settle money on the chosen subset.

| Game | Include (mode) | Exclude | Rate / settle on | Drop (store but never wager) | History floor | Placement system |
| --- | --- | --- | --- | --- | --- | --- |
| **CS2** | **Competitive only** | Premier, Wingman, casual, all others | `cs2_kills` (primary), `cs2_kd_ratio` (secondary), `cs2_score` (optional, later) | `cs2_headshot_pct` | 0 | **System 2 — no history** |
| **Chess** | **Blitz and Rapid, as two separate markets** | Bullet, Classical, casual, variants, correspondence, vs-computer | `chess_moves` (per speed) | accuracy (no live source) | 20 rated | **System 1 — history** |
| **Dota 2** | **Ranked matchmaking only** | Turbo, unranked, lobbies/custom, event | `dota2_gpm` (primary), `dota2_kda_ratio` (secondary) | — | 25 | **System 1 — history** |
| **PUBG** | **Official BR modes, as is** (solo/solo-fpp/duo/duo-fpp/squad/squad-fpp; matchType official/competitive) | custom, arcade, war, event, training | `pubg_damage` (primary), `pubg_kills` (secondary) | `pubg_headshot_pct` | 20 | **System 1 — history** |

**The markets this produces** (a market = `game × mode × metric`, each with its own buckets,
reference and bars):

- CS2: `(cs2, competitive, kills)`, `(cs2, competitive, kd_ratio)` — plus `(cs2, competitive, score)` later.
- Chess: `(chess, blitz, moves)`, `(chess, rapid, moves)` — **two independent markets, never pooled.**
- Dota 2: `(dota2, ranked, gpm)`, `(dota2, ranked, kda_ratio)`.
- PUBG: `(pubg, official, damage)`, `(pubg, official, kills)`.

**Why these metrics (the rule to apply to any future metric):** counts and per-time rates are
**safe** (kills, damage, GPM, moves, score) — the player can't shrink the denominator. Ratios
are **risky / heavy-tailed** (K/D, KDA) — keep them as *secondary* and give their bars
robust, heavy-tail-aware placement. Percentages divided by the player's own volume are
**exploitable** (headshot % = headshots ÷ *your* kills → one kill + one headshot → 100%) — so
they are dropped from wagering and kept for display only.

**The two placement systems (which game is which):**

- **System 1 — games with history (Chess, Dota, PUBG).** At link we backfill recent matches up
  to the floor, compute a settled index, place the player in a real bucket *before they wager*,
  and allow normal stakes once `n ≥ floor`. Detailed in Phase 4.
- **System 2 — games without fetchable history (CS2).** The share-code chain only moves forward,
  so there's nothing to backfill. The player bets from match one, but at a **confidence-gated
  stake ladder** ($5 → $10 → $25 → uncapped) that only opens as their index settles. Detailed in
  Phase 4; this is also the smurf defense.

**Implementation flags to resolve while building:**

- **CS2 "Competitive only" needs a mode discriminator.** Share codes come from Premier,
  Competitive *and* Wingman. Wingman is excluded trivially (roster ≤ 4). Separating **Premier vs
  Competitive** requires reading the match's mode/type from the GC resolve; if the payload can't
  distinguish them, that is a real gap to close in the CS2 adapter before enabling the market —
  flag it, don't guess.
- **Dota "ranked only" adds a gate that doesn't exist yet.** `lobby_type` and `game_mode` are
  read but not filtered today. Enforce `lobby_type = ranked (7)` and exclude Turbo (`game_mode`
  23) and other non-standard modes in `_normalize`.
- **Chess must key markets by speed.** Reuse the existing `requires_speed`; `blitz` and `rapid`
  each get their own reference, cuts and bars — a blitz move count and a rapid move count are
  never compared.
- **PUBG stays pooled across official modes for now** (the cross-mode residual is accepted, as in
  the reference doc). Per-mode splitting (solo vs squad) is a future market subdivision.

---

## Phase map (at a glance)

| Phase | Delivers | Gate you unlock |
| --- | --- | --- |
| 0 | Data model + migrations | schema is real & idempotent |
| 1 | Idempotent ingestion (record every match, store everything) | the ML corpus starts filling, no double counts |
| 2 | Skill index (best-of-40%) + Welford state | sandbagging is defeated by construction |
| 3 | Reference distributions, bucket cuts, assignment | players land in buckets, reproducibly |
| 4 | Placement: two systems + smurf-safe stake ladder | new players onboard safely (history & no-history) |
| 5 | Matchmaking + settlement + money invariant | **a real wager settles end to end** |
| 6 | Disputes + audit trail | **beta-ready: every contest is reconstructable** |
| 7 | Auto-promotion / demotion (the three gates) | buckets grow on their own as you scale |
| 8 | Monitoring, scale hardening, ML-readiness | sustainable at large player counts |

---

# Phase 0 — Data model & migrations

**Goal.** Create the tables the whole system reads and writes, with the constraints that
make later phases safe (idempotency, versioning) baked in from day one.

**Why.** Getting the schema right first means idempotency and audit are *structural*, not
bolted on later. Adding a `UNIQUE` constraint after you already have duplicate rows is a
painful migration; adding it now is free.

### Build

Five tables (full DDL in the delivered `schema.sql`; summarized here):

- **`game_links`** — which external accounts a player has linked. `UNIQUE(game, external_id)`.
- **`match_stats`** — the append-only raw event log. One row per finished, gradable match
  per linked player. Stores **every** field the adapter saw (not just rated metrics) in a
  `metrics JSONB` column. **`UNIQUE(player_id, game, host_match_id)`** ← the idempotency key.
  Partitioned by `created_at_ms` (monthly).
- **`market_state`** — derived per-player, per-`(game, mode, metric)` state: running
  `mean`, `m2` (Welford), `best_window` (last 20), `index_value`, `index_confidence`,
  `bucket`, `bucket_version`, `placed_from`. Small; updated in place.
- **`market_reference`** — versioned, seasoned cut points + bar-per-bucket per market.
  `PRIMARY KEY(game, mode, metric, season, version)`, one row `active=true` per market.
- **`settlement`** — the audit row: which `bucket`, `bar`, `reference_version` graded each
  contest, plus stake/payout. `PRIMARY KEY(contest_id, player_id)`.

Plus two tables introduced in Phase 6 (create the migrations now, empty):

- **`disputes`** — dispute lifecycle.
- **`audit_events`** — append-only log of anything that touched money or placement.

### Test gate

- [ ] **Migration up/down runs clean** on an empty DB and is reversible.
- [ ] **The test fixture builds the schema via migrations**, not `create_all` (ground rule 5).
- [ ] **Idempotency constraint exists and bites**: inserting two `match_stats` rows with the
      same `(player_id, game, host_match_id)` raises a unique-violation.
- [ ] **Partitioning works**: rows route to the correct monthly partition; a query spanning
      two months returns all rows.
- [ ] **`market_reference` allows exactly one active row per market** (partial unique index
      on `active=true`), tested by trying to activate two versions at once.

---

# Phase 1 — Idempotent ingestion (record everything, once)

**Goal.** Every finished, gradable match a linked player produces is written to
`match_stats` exactly once, storing all available fields.

**Why.** This log is two things at once: the **settlement source of truth** and the
**training corpus for later ranking/sorting**. If it double-counts, stats inflate and money
is wrong. If it stores only what we rate on today, a future model has nothing new to learn
from. Both failures are prevented here.

### Build

- A single `record_match(player, game, norm_game)` entry point (call it from the existing
  settlement worker / poller). It:
  1. Checks the idempotency key; if the match is already recorded, **returns without
     writing** (safe to call repeatedly — the poller *will* re-see matches).
  2. Writes one `match_stats` row with `metrics = { every field the adapter exposed }`.
- **Store more than you rate on** — per game, the `metrics` JSON includes *every* field the
  adapter exposed (the ML fuel), even though we only build markets on the subset in the **Launch
  scope** table above. Storing a field is free and future-proof; not storing it is unrecoverable.
  The full per-game field lists:
  - **CS2:** `kills, deaths, assists, headshots, mvps, score, rounds`
  - **Chess:** `moves, result, opp_rating, time_control`
  - **Dota:** `kills, deaths, assists, gpm, xpm, duration, hero_id, lobby_type, game_mode`
  - **PUBG:** `kills, damage, headshotKills, assists, DBNOs, timeSurvived, walkDistance, revives, winPlace`
- **Keep identity out of the log.** `match_stats` references the internal `player_id`; the
  external handle / KYC / wallet mapping lives in `game_links` and other tables. This makes
  the corpus pseudonymous by construction.
- **Idempotency must be concurrency-safe**: use `INSERT … ON CONFLICT DO NOTHING`, not a
  read-then-write (two workers can read "absent" simultaneously).

### Test gate

- [ ] **Re-ingesting the same match is a no-op**: call `record_match` twice → one row.
- [ ] **Concurrent ingestion is safe**: two parallel `record_match` calls for the same match
      → exactly one row (test with a real DB and two connections).
- [ ] **Every adapter's unused fields land in `metrics`** (one assertion per game, from a
      captured fixture response).
- [ ] **Only finished, gradable matches are recorded** — a surrender/abandon below the round
      floor, a non-standard chess variant, a custom PUBG match, etc. are skipped (reuses the
      adapters' existing `_normalize` rules).
- [ ] **No external handle or PII appears in `match_stats`.**

---

# Phase 2 — The skill index (best-of-40%), with Welford

**Goal.** Turn each player's recent results into one skill number per market, computed so
that throwing games can't lower it.

**Why (the anti-sandbag defense).** The index = **mean of the best 40% of the last 20
results** (this is your existing design). A thrown game is not in your best 40%, so its
weight on the index is ~zero — sandbagging (deliberately losing to drop your rank and farm
weaker opponents) is defeated *by construction*, with no detector needed. If you used a plain
average instead, a few thrown games would tank the number and the whole ladder would be
farmable.

> **Sandbagging vs smurfing — keep them separate.** Best-of-40% here defeats **sandbagging**
> (an *existing* account throwing games). **Smurfing** (a *strong player on a fresh account*)
> is a different problem handled in Phase 4 (conservative placement + capped stakes + fast
> re-rating), because a fresh account has no history for best-of to protect.

### Build

- `update_index(player, game, mode, metric, value)`:
  - **Welford update** of `mean`, `m2`, `n_samples` (so variance is O(1) per match, never a
    rescan of the log).
  - Push `value` into `best_window` (rolling last 20).
  - Recompute `index_value` = mean of the best `k = max(3, ceil(0.40 × len(window)))` of the
    window. For `METRIC_LOWER_IS_BETTER` metrics (chess moves), "best" = the *lowest* values.
  - Apply **rise-fast / fall-slow**: `index = raw if raw > index else index + 0.25·(raw − index)`,
    floored at the 12-month peak minus one bucket. (Rise instantly on improvement; fall at a
    quarter rate so one bad night — or a deliberate one — can't crater the number.)
  - Respect the existing metric guards: `METRIC_REQUIRES_WIN` (chess moves count only on a
    win), `METRIC_FLOOR` (moves floor 2.0), positive-support handling.
- Compute `index_confidence` from the standard error (`σ/√n`) — 0 when the number is still
  moving, → 1 as it settles. Phase 4 uses this to gate stakes.
- **Determinism is required** (this feeds the money path): identical inputs → identical index,
  across runs and machines. Pin any library used; add a determinism test.

### Test gate

- [ ] **Sandbag property (the headline test):** take a settled history, then append up to 12
      deliberately-thrown games (value ≈ 0). Assert the index moves by less than one bar
      increment until the thrown count is implausibly large (>~half the window). A plain
      average, run alongside, must visibly collapse — proving best-of is doing the work.
- [ ] **Best-of correctness:** index equals the analytic mean-of-top-40% on a known fixture,
      to a stated tolerance.
- [ ] **Lower-is-better:** chess-moves index uses the lowest values and respects the floor of 2
      and requires-win.
- [ ] **Rise-fast / fall-slow:** a single great game jumps the index immediately; a single bad
      game moves it ~¼ of the gap; the 12-month floor holds.
- [ ] **Welford matches batch:** running mean/variance equals a from-scratch recompute over the
      same samples (property test over random inputs).
- [ ] **Determinism:** same inputs → identical index bytes across two runs.
- [ ] **Golden snapshot:** a fixed set of players → a checked-in table of indices; any change
      to it must be reviewed in the diff.

---

# Phase 3 — Reference distributions, bucket cuts & assignment

**Goal.** Cut each market's skill line into buckets, and place each player in one —
reproducibly, and seeded from public data so it works before we have our own population.

**Why.** This is the "bucketing" itself. Two properties matter: it must be **reproducible**
(the same player must always land in the same bucket on the same data — so no k-means on 1-D;
use quantile or Fisher-Jenks cuts), and it must **not flap** at boundaries (hysteresis).

### Build

- **Reference seeding.** For each launch market, compute cut points from public/captured
  distribution data. Store as `market_reference` version 1, `source='public'`, one bar per
  bucket = `bucket_median + margin`. Start with **K = 3** (justified in Phase 7).
  - Cut method: **minimum-within-variance** (Fisher-Jenks / 1-D DP) with a **population floor**
    per bucket, because one-bar-per-bucket fairness depends on skill-tightness. (Equal-population
    quantile cuts are the fallback when a market is so small that even the floor can't be met —
    they guarantee every bucket fills.)
- **Assignment.** `bucket(index) = searchsorted(cut_points, index)` — count cut points below
  the index. O(log K).
- **Hysteresis.** Only move a player to a new bucket when their index crosses the boundary by a
  margin (e.g. 15% of a bucket width), and never drop more than one bucket at once. This is the
  "debounce" that stops boundary players thrashing.
- Everything reads the **active** reference version and records `bucket_version` on the player's
  state.

### Test gate

- [ ] **Reproducibility:** the same index against the same reference → the same bucket, every
      call. (Explicitly assert we did *not* use a non-deterministic clusterer.)
- [ ] **Assignment correctness:** boundary values land on the documented side (define whether a
      value exactly on a cut goes up or down, and test it).
- [ ] **Hysteresis:** a player oscillating around a boundary by less than the margin does **not**
      change bucket; one that crosses by more than the margin does.
- [ ] **Grouping is by level, not variance or playstyle:** build a population with independent
      level / erraticness / playstyle; assert average level rises across buckets while average
      erraticness and playstyle stay flat. (Guards against accidentally bucketing on the wrong axis.)
- [ ] **Version isolation:** assigning under version N and version N+1 are independent; changing
      the active version never mutates historical `settlement` rows.

---

# Phase 4 — Placement: two systems + smurf-safe stake ladder

**Goal.** Onboard a new player correctly whether or not we can fetch their history, and make a
misplacement cost only a few dollars.

**Why (the smurf defense).** A player's first placement is a guess. For chess/Dota we can make a
*good* guess from history; for CS2 we can't (no fetchable past), so a strong player on a fresh
CS2 account (a **smurf**) will be underrated at first. We bound the damage with a **stake ladder
gated on index confidence**, not on raw game count — so the cap only opens once the number has
stopped moving, which is exactly when a smurf has been caught up to.

### Build

(Which game is which system is fixed in the **Launch scope** table above: CS2 → System 2; Chess,
Dota, PUBG → System 1.)

- **System 1 — history exists (chess floor 20, Dota 25, PUBG 20).** At link, backfill recent
  matches up to the floor via the adapter, run them through `record_match` + `update_index`,
  place confidently, `placed_from='history'`. Normal stakes once `n ≥ floor`.
- **System 2 — no history (CS2 floor 0).** Seed a weak prior from Steam lifetime stats (often
  missing → then start at the lowest bucket, conservative). `placed_from='prior'|'live'`. Bet
  from match one, but stake-capped:
  - Ladder `$5 → $10 → $25 → uncapped`, indexed by `index_confidence` (settled number → higher
    rung). While the index is still climbing (a smurf, or a genuine learner) the cap stays low.
- **Provisional gating** (reuse existing constants): a stat market is provisional below
  `METRIC_PROVISIONAL_MIN_N = 10` graded samples; pools quote a bar from
  `STAT_BASELINE_MIN_N = 1`. Provisional = capped stakes regardless of game.
- **Exceptional-result fast re-rate:** a result far above the player's current index pulls the
  index up immediately and retroactively (already implied by rise-fast) — this is what makes a
  smurf's underrating short-lived.

### Test gate

- [ ] **System 1 backfill:** a linked chess/Dota account with ≥ floor history is placed
      non-provisionally at link, in the bucket its history implies.
- [ ] **System 2 cap:** a fresh CS2 account can wager at match 1, but the max stake equals the
      ladder floor until confidence rises; assert the cap schedule.
- [ ] **Smurf extraction is bounded:** simulate a strong player on a fresh CS2 account; assert
      total winnings before the index reaches their true level stay within a small bound (a few
      × the floor stake), because the cap is confidence-gated.
- [ ] **Cap unlocks on stability, not count:** a still-climbing index keeps the low cap even past
      the game count; a settled index unlocks the ladder.
- [ ] **Provisional flips at the right N** for both stat markets and pools.
- [ ] **Genuine improver is not punished:** a real improver's cap rises as their index settles;
      they are never blocked or banned (only briefly capped).

---

# Phase 5 — Matchmaking, settlement & the money invariant

**Goal.** Form rooms from a bucket, settle against the one bar, and never lose or create a cent.

**Why.** This is where money moves, so it's where the invariants must be enforced in code, not
just hoped for. A bucket is both the grouping and the matchmaking pool.

### Build

- **Queue by bucket.** A player with an open wager joins their `(game, mode, metric, bucket)`
  queue. A room of `ROOM` players forms from that queue within a fill window (async — nobody has
  to be online at once).
- **One bar per bucket.** All room members settle against `market_reference.bar_per_bucket[bucket]`.
- **Settlement** (reuses the existing `stat_race` / pool resolution kinds): those who clear the
  bar split the pot; **nobody clears → full refund** (no rake); **lopsided/unfillable room →
  refund and re-queue** (never widen past the fairness budget).
- **Money invariant, enforced:** before a settlement commits, assert
  `sum(payouts) + rake == pot` to the cent; if it fails, **abort and refund** (fail closed).
- **Write the `settlement` audit row** with the exact `bucket`, `bar`, `reference_version`,
  `result_value`, stake, payout — this is what Phase 6 reconstructs from.

### Test gate

- [ ] **Money invariant holds** across thousands of randomized contests (property test):
      `sum(payouts) + rake == pot`, always, to the cent.
- [ ] **No-clear refund:** when nobody beats the bar, everyone is refunded and rake is zero.
- [ ] **Fail-closed on bad data:** a missing/unverifiable result (CS2 sidecar down, PUBG 5xx)
      voids and refunds the contest; no settlement row with a guessed value is ever written.
- [ ] **Rounding is exact:** payouts use integer cents; the invariant test includes pots that
      don't divide evenly among winners.
- [ ] **Every settlement writes a complete audit row** (bucket, bar, version present and correct).
- [ ] **Fill behaves:** at low traffic, small rooms + a long window fill; a bucket that can't
      fill refunds rather than mismatching.

---

# Phase 6 — Disputes & audit trail (beta-ready trust layer)

**Goal.** Any past contest can be fully reconstructed, and a player who disputes a result gets a
fair, fast, auditable process.

**Why.** Real money means real disputes. If you can't answer "why did this grade the way it did?"
you lose the dispute and the user. Because we versioned everything in Phases 3 and 5, the answer
is always reconstructable — this phase exposes it and adds the workflow.

### Build

- **`audit_events`** (append-only): every event that touched money or placement — index recompute,
  bucket change, reference version activation, settlement, refund, stake-cap change. Each row:
  `player_id, event_type, market, before/after JSONB, actor (system|admin|job), created_at`.
  Never updated or deleted.
- **Reconstruction endpoint:** given a `contest_id`, return the full story — the players' indices at
  the time, the active `reference_version`, the cut points and bar used, each result, and the payout
  math — read entirely from `settlement` + `audit_events` + the versioned `market_reference`. No
  guessing, no "current" values substituted for historical ones.
- **`disputes`** lifecycle:
  `open → under_review → (resolved_no_change | resolved_refund | resolved_adjust) `.
  Opening a dispute **snapshots** the relevant audit/settlement rows (so later changes can't alter
  the evidence) and can place a **hold** that blocks payout/withdrawal on the affected contest until
  resolved.
- **Admin actions are themselves audited** (an admin refund writes an `audit_events` row with
  `actor='admin'` and a reason), so the audit trail can't be quietly edited.

### Test gate

- [ ] **Reconstruct a historical settlement:** after activating a *newer* reference version, a
      contest settled under the old version still reconstructs with the **old** cut points and bar
      (proves version isolation end to end).
- [ ] **Audit completeness:** every money/placement mutation produces exactly one `audit_events`
      row; a settlement with no audit row fails a consistency check.
- [ ] **Dispute lifecycle:** open → hold blocks payout → resolve_refund releases the correct amount;
      resolve_no_change releases the original payout; all transitions audited.
- [ ] **Evidence is immutable:** a dispute's snapshot doesn't change when later matches/recomputes
      happen.
- [ ] **Audit log is append-only:** attempts to update/delete `audit_events` are rejected (DB
      permission or trigger).

---

# Phase 7 — Auto-promotion / demotion (buckets grow on their own)

**Goal.** Each market gains a bucket when it can support one and loses a bucket when it can't —
decided automatically, applied safely.

**Why.** Three buckets is right at launch, but a growing market should get finer divisions without
anyone hand-tuning. The decision is automatic (three measurable gates); the *application* is a
controlled, versioned event so money and ranks are never disturbed silently.

### Build

- **Nightly `evaluate_market(game, mode, metric)`** computes the three ceilings and proposes a K:
  - **Precision:** narrowest proposed bucket width `> 2 × (σ_match / √(median matches per player))`.
  - **Stability:** bootstrap the proposed cut points; wobble `< 10%` of a bucket width.
  - **Liquidity:** every proposed bucket's daily pool fills a room `≥ 90%` of days.
  - Eligible K = largest K passing all three; flag promote (K+1) or demote (K−1).
- **Controlled re-cut** (never live/silent):
  - Compute the new versioned `market_reference` (new cut points + bars), `source='ours'` once the
    population is representative, else keep `'public'`.
  - **Freeze settlement** for the market during the swap; activate the new version atomically.
  - Re-bucket all players under hysteresis; **hide the old bucket number, reveal the new** (present
    as a "season" — the ladder expanded), and **announce** it. Write `audit_events` for the re-cut.
- Re-cuts run on a **season cadence** or an on-demand migration window — the gates decide *whether*,
  the schedule decides *when*.

### Test gate

- [ ] **Gate math:** on synthetic populations of known size, `evaluate_market` returns the expected
      K and names the binding gate (matches `promotion.py` output).
- [ ] **Promotion migration:** a 3→4 re-cut produces a new version, re-buckets players, and leaves
      all prior `settlement` rows untouched and still reconstructable.
- [ ] **Settlement freeze:** no contest is graded across the version swap (no settlement rows with a
      half-applied table).
- [ ] **Demotion:** a market that loses players (a bucket stops filling) proposes and applies a
      merge to K−1 through the same safe path.
- [ ] **No silent live re-cut:** assert the system never activates a new reference outside a
      freeze/migration window.
- [ ] **Announcement/display:** the re-cut emits the event the UI uses to show "ladder expanded"
      rather than a rank drop.

---

# Phase 8 — Monitoring, scale hardening & ML-readiness

**Goal.** Keep it healthy at large player counts, and make the recorded data actually usable for a
future ranking/sorting model.

**Why.** Everything can be correct and still fall over at scale, or leave you with a data lake you
can't train on. This phase closes both.

### Build

- **Per-market dashboard — the four numbers** from the deep-dive: rated players (N), median matches
  per player (n), per-bucket fill rate, boundary wobble. These drive promote/demote and surface a
  starving bucket early.
- **Scale hardening:** confirm `match_stats` partition rollover + cold archival; confirm placement
  reads only the small `market_state` row on the hot path (never scans the log); the nightly
  bucket/promotion jobs are batch, not request-time.
- **Patch-drift watch:** monitor each market's live distribution; when a game patch shifts it,
  auto-open a new `season` and freeze settlement until re-baselined.
- **Fraud/anomaly hook (derivative watchdog):** a job flags accounts whose index jumps abnormally
  (bought/boosted accounts) → **stake hold + human review**, never an automatic ban. (Detection, not
  the rating — the rating stays best-of.)
- **ML-readiness checkpoint:** confirm the corpus is trainable — full stat vectors present, keyed by
  internal id (pseudonymous), labeled with outcome, exportable as a point-in-time snapshot. Document
  that ML is for **learning index weights, playstyle hints, and fraud** — *not* for the bucketing
  itself (which stays reproducible bands).

### Test gate

- [ ] **Load test:** placement + settlement hold their latency target at target concurrency; the log
      write is the only unbounded-growth table and it partitions cleanly.
- [ ] **Hot path never scans the log:** a query counter proves placement reads O(1) rows.
- [ ] **Archival round-trip:** a cold partition can be detached and a historical reconstruction still
      succeeds (from archive if needed).
- [ ] **Patch-drift trigger:** a simulated distribution shift opens a new season and freezes
      settlement.
- [ ] **Anomaly flag routes to review, not ban:** a synthetic account-takeover pattern raises a flag
      + stake hold and touches no money automatically.
- [ ] **Corpus export is pseudonymous and complete:** an export contains full stat vectors and
      outcomes, and no external handle/PII.

---

## Cross-cutting concerns (verify in every phase, not just once)

| Concern | Where it's enforced | How it's tested |
| --- | --- | --- |
| **Idempotency (no double-count)** | Phase 1 unique key + `ON CONFLICT DO NOTHING` | re-ingest & concurrent-ingest tests |
| **Sandbagging** | Phase 2 best-of-40% index | "throw 12 games, index barely moves" test |
| **Smurfing** | Phase 4 conservative placement + confidence-gated cap + fast re-rate | bounded-extraction simulation |
| **Money integrity** | Phase 5 invariant assert + fail-closed | randomized-pot property test |
| **Disputes/trust** | Phase 6 audit trail + reconstruction | reconstruct-old-version test |
| **Fairness of the shared bar** | Phase 3 min-variance cuts; Phase 7 grows K | grouping-by-level + edge-ratio tests |
| **Scale/ML** | Phase 8 partitioning + corpus checkpoint | load test + pseudonymity export |

---

## Suggested delivery order & milestones

- **Milestone A — "it records" (Phases 0–2).** The corpus is filling idempotently and the index is
  sandbag-proof. No money yet. Safe to run in shadow against real traffic behind a flag.
- **Milestone B — "it settles" (Phases 3–5).** A real wager places, matches, and settles with the
  money invariant enforced. Internal alpha.
- **Milestone C — "it's trustworthy" (Phase 6).** Disputes + audit make it safe to put in front of
  real users. **Beta launch here.**
- **Milestone D — "it scales itself" (Phases 7–8).** Buckets grow automatically; monitored and
  hardened for large populations and a future ranking model.

Each phase's test gate must be green — run the full suite plus the golden-snapshot harness and the
money-invariant tests — before the next phase begins. That is what makes this safe to run on real
users with real money.
