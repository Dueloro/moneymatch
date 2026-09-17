# Money Match — Bucketing System: Technical Walkthrough

The companion to `IMPLEMENTATION_BUCKETING.md`. That file says **what to build and how to
test it, phase by phase**. This file says **how it actually works** — how data moves through
the services, how the backend pieces talk to each other, what the API does on each call, and
what the frontend sends and shows. Read this to understand the machine; read the other to
build it in order.

Written so that when you hand a phase to Claude (or an engineer), it knows exactly what calls
what, in what order, and where state lives.

---

## 0. The cast — the services and who talks to whom

There are five moving parts. Keep them straight and everything else follows.

- **Frontend** (`apps/web` / mobile) — the only thing the user touches. It never computes an
  index or a bucket; it *reads* state the backend already computed and *sends* intents (link
  this account, enter this wager, open this dispute).
- **API** (`apps/api`, the FastAPI service) — the synchronous front door. It answers the
  frontend, reads/writes Postgres, holds/releases money in the wallet, and **enqueues** slow
  work rather than doing it inline. It never calls a slow external game API in a request.
- **Worker** (background process, same codebase) — the asynchronous engine. It polls the game
  hosts, runs the adapters, records matches, updates indices and buckets, forms rooms, and
  settles contests. Everything that touches an external API or takes more than a few
  milliseconds happens here.
- **GC sidecar** (`gc-sidecar/`) — a tiny separate process that speaks CS2's Game Coordinator
  protobuf (Python can't). The worker calls it over HTTP: "here's a share code, give me the
  scoreboard." It exists only because CS2 stats are unreachable any other way.
- **Postgres** — the single source of truth (the tables in `schema.sql`). **Redis** sits beside
  it as the queue + short-TTL cache (e.g. PUBG's rate-limited match cache).

The rule that makes it scale: **the API is fast and never blocks on a game host; the worker is
where the waiting happens.** The frontend talks only to the API; the API and worker communicate
only through Postgres rows and Redis jobs — never by calling each other directly.

```
frontend ──HTTP──> API ──rows/jobs──> Postgres / Redis <──rows/jobs── Worker ──HTTP──> game hosts
                                                                          └─HTTP──> GC sidecar (CS2)
```

---

## Launch scope — games, modes & metrics (read before §1)

This is the authoritative scope both this file and `IMPLEMENTATION_BUCKETING.md` build to. It
decides which matches the adapters let through, which metrics become bucketed markets, and which
placement system a game uses. Note the split: the worker **stores every field** of every match
(the ML corpus), but only the "rate on" subset becomes a market you can wager in.

| Game | Include (mode) | Exclude | Rate / settle on | Drop (store, never wager) | Placement |
| --- | --- | --- | --- | --- | --- |
| **CS2** | **Competitive only** | Premier, Wingman, casual | `cs2_kills`, `cs2_kd_ratio`, (`cs2_score` later) | `cs2_headshot_pct` | **System 2 — no history** |
| **Chess** | **Blitz & Rapid, separate markets** | Bullet, Classical, casual, variants, vs-computer | `chess_moves` (per speed) | accuracy | **System 1 — history** |
| **Dota 2** | **Ranked matchmaking only** | Turbo, unranked, custom, event | `dota2_gpm`, `dota2_kda_ratio` | — | **System 1 — history** |
| **PUBG** | **Official BR modes, as is** | custom, arcade, war, event, training | `pubg_damage`, `pubg_kills` | `pubg_headshot_pct` | **System 1 — history** |

**Markets** (a market = `game × mode × metric`): `(cs2, competitive, kills/kd_ratio)`,
`(chess, blitz, moves)` and `(chess, rapid, moves)` as two separate markets, `(dota2, ranked,
gpm/kda_ratio)`, `(pubg, official, damage/kills)`. Each market has its own reference, cut lines
and bars.

**Where in the code each rule lives:** the *mode* include/exclude is enforced in the game's
adapter `_normalize` (a match in an excluded mode is dropped before it's ever recorded — CS2
must additionally distinguish Competitive from Premier/Wingman; Dota must gate `lobby_type`/
`game_mode` to ranked, a filter that does not exist yet; chess keys the market by `speed`). The
*rate-on* subset is the metric allowlist per market in `constants.py`. The full field set is
still stored in `match_stats.metrics` regardless (§3).

**The two placement systems, mapped:** **System 1** (Chess, Dota, PUBG) fetches history at link
and places confidently — §6. **System 2** (CS2) has no fetchable history, so it bets from match
one under a confidence-gated stake ladder — also §6, and it's the smurf defense.

**Metric-choice rule** (apply to any future metric): counts/rates are safe (kills, damage, GPM,
moves, score); ratios are heavy-tailed so they're secondary with robust bars (K/D, KDA);
own-volume percentages are exploitable so they're dropped from wagering (headshot %).

---

## 1. The spine — one wager, end to end

Before the per-phase detail, here is the whole life of a single wager as one story. Everything
later is a zoom-in on a step here.

1. **Link.** The user links their CS2/chess/Dota/PUBG account in the app. The frontend POSTs
   the handle to the API. The API verifies the account exists (and, for Dota, that public match
   data is exposed; for CS2, that it's a valid Steam account with no blocking ban), writes a
   `game_links` row, and — if the game has fetchable history — **enqueues a backfill job**. It
   returns immediately; the heavy lifting is now the worker's problem.

2. **Ingest / backfill.** The worker picks up the job, calls the game host's API, and for each
   finished match runs the game's **adapter** (`adapters/…`) which normalizes the raw host JSON
   into a `NormGame`. It calls **`record_match`** (append-only, idempotent insert into
   `match_stats`, storing *every* field), then **`update_index`** (Welford + best-of-40%), then
   **assigns a bucket** (searchsorted + hysteresis). The player's `market_state` row now holds a
   skill index, a confidence, and a bucket for each market they play.

3. **Browse & enter a wager.** The user opens a market in the app. The frontend GETs
   `/markets`, which returns, for each market: the user's bucket, that bucket's **one bar**,
   their current **stake cap**, and the payout math. The user picks a stake and confirms. The
   API validates (are they allowed to wager here? is the stake within their cap?), **holds the
   stake** in the wallet, creates a `contest` entry, and drops the player into the
   `(game, mode, metric, bucket)` **queue**.

4. **Match.** The worker's matchmaker pulls players from that bucket's queue and forms a room
   of `ROOM` players within a fill window. Nobody has to be online at once — a "room" is just a
   set of open wagers in the same bucket during the same window.

5. **Settle.** Each player then plays a real game. The worker's poller sees the new match come
   through the *same ingest path* as step 2, recognizes it as the qualifying match for an open
   contest, and settles: it compares each player's result to the bucket bar, computes payouts
   (asserting `sum(payouts) + rake == pot`), writes a `settlement` audit row (with the exact
   bar and reference version used) and `audit_events`, and releases money through the wallet —
   or refunds everyone if nobody cleared or the data couldn't be verified.

6. **See the result.** The frontend, which has been polling the contest's status endpoint, shows
   the outcome. If the user disagrees, they open a dispute, which snapshots the evidence and can
   hold the payout until an admin resolves it.

7. **Overnight.** Batch jobs recompute each market's reference (bucket lines + bars), evaluate
   whether a market has earned another bucket, and roll up the monitoring numbers.

That's the entire system. Now the zoom-ins, aligned to the implementation phases.

---

## 2. Data model — how state is laid out (Phase 0)

Three kinds of state, and it's worth understanding *why they're separate* because it dictates
which service writes what.

- **The raw log — `match_stats`.** Append-only, one row per finished match per player, every
  field in a `metrics JSONB`. Only the **worker** writes it (during ingest). It's the settlement
  source of truth *and* the future-ML corpus. It grows forever, so it's **partitioned by month**;
  nothing on the hot path ever scans it.
- **The derived state — `market_state`.** One small row per `(player, game, mode, metric)`. Holds
  the running mean/variance (Welford), the last-20 window, the index, the confidence, the bucket.
  The **worker** updates it on each new match; the **API** *reads* it to answer "what's my bucket
  and bar and cap?" This is the only table the hot path touches per player, and it's tiny.
- **The reference — `market_reference`.** The bucket lines and bars, **versioned** and
  **seasoned**. A **nightly batch** writes new versions; the worker and API read the `active` one.
  Because it's versioned, a re-cut never destroys the lines a past contest was graded against.
- **The audit — `settlement` + `audit_events`.** Written by the worker whenever money or
  placement changes. Never updated, never deleted. This is what disputes read.

The mental model: **the log is history, the state is now, the reference is the ruler, the audit is
the receipt.** Each is written by exactly one kind of process, which is what keeps writes from
racing each other.

---

## 3. Ingestion — how a match becomes a row (Phase 1)

This is the worker's core loop, and it's the same path whether it's a backfill at link time or a
live poll later. Here's how the data actually moves.

The worker keeps, per linked account, a **cursor** — for CS2 it's the last share code in the
chain; for Lichess/OpenDota/PUBG it's a timestamp or the newest match id it has seen. On each
tick it asks the host "anything newer than my cursor?"

- **CS2** is the awkward one. The worker calls the Steam Web API `GetNextMatchSharingCode` to walk
  the share-code linked list forward; each new code is handed to the **GC sidecar** over HTTP,
  which resolves it to a scoreboard (kills/deaths/etc. for all ten players). The nine other
  players in that scoreboard are a free "players near my rank" read the reference job can later use.
- **Chess** streams the Lichess NDJSON game feed; **Dota** reads OpenDota `recentMatches`; **PUBG**
  fetches match ids from the player resource, then each `/matches/{id}` — but throttled to
  ~10 req/min with a Redis TTL cache, which is why PUBG defers its backfill to the worker instead
  of doing it inline at link.

Whatever the host, the raw JSON goes into that game's **adapter**, whose `_normalize` turns it into
a `NormGame` (or drops it if it's not a finished, gradable, right-mode match). Then:

1. **`record_match`** runs `INSERT … ON CONFLICT (player_id, game, host_match_id) DO NOTHING`. This
   single line is the idempotency guarantee: the poller *will* re-see the same match on the next
   tick, and two workers might process it at once, and it still lands exactly one row. No
   read-then-write (that races); the database's unique index is the arbiter.
2. If the insert actually happened (not a conflict), it calls **`update_index`** (next section).

The important interaction: **ingestion never talks to the API or the frontend.** It just writes
rows. The API later reads those rows. That decoupling is what lets the worker fall behind or catch
up without the app noticing anything but fresher numbers.

---

## 4. The skill index — how a pile of matches becomes one number (Phase 2)

This runs inside `update_index`, entirely on the worker, and it's pure arithmetic on the player's
own `market_state` row — no log scan.

When a new value arrives for a metric, the worker does a **Welford update**: it nudges the running
`mean` and `m2` (from which variance is `m2/(n−1)`) in O(1), and pushes the value into the rolling
`best_window` of the last 20. Then it computes the **index**: sort the window, take the best
`k = max(3, ceil(0.40 × window_size))` values (the *lowest* for lower-is-better metrics like chess
moves), average them. That "best 40%" is the whole anti-sandbag trick — a thrown game sits in the
*worst* 60%, so it never enters the average, so deliberately losing can't lower your number.

Then it applies **rise-fast / fall-slow**: if the fresh index is higher than the stored one, take it
immediately; if lower, move only 25% of the way down, and never below the 12-month peak minus one
bucket. So a good game lifts you now, a bad game (or a tanked one) barely dents you.

Finally it computes **`index_confidence`** from the standard error `σ/√n` — near 0 while the number
is still swinging, climbing toward 1 as it settles. This single number is what Phase 4 reads to
decide how much a new player may stake.

The output is written back to the same `market_state` row. Nothing downstream recomputes the index;
everyone else just reads `index_value`, `index_confidence`, and `bucket`.

---

## 5. Buckets — how the number becomes a rank (Phase 3)

Two very different cadences, and it's the key to understanding this part: **drawing the lines is
rare and heavy; placing a player is constant and trivial.**

- **Drawing the lines** happens in a **nightly batch**, per market. It reads the population of
  indices (or, at launch, public seed data), runs the minimum-variance cut algorithm (Fisher-Jenks
  / 1-D k-means) with a per-bucket population floor, and writes the result as a **new
  `market_reference` version** with one bar per bucket (`bucket_median + margin`). It flips
  `active` to the new version atomically. This is seconds of work, done once a night, off the hot
  path.
- **Placing a player** happens every time their index changes, inside the worker right after
  `update_index`. It reads the active reference's cut points and does one `searchsorted`:
  `bucket = number of cut lines below the index`. Then **hysteresis**: it only actually changes the
  stored bucket if the index has crossed the boundary by a margin (≈15% of a bucket width), and
  never drops more than one bucket at once — so a player hovering on a line doesn't flip every
  match. The new bucket + the `bucket_version` it came from are written to `market_state`.

The API never computes any of this. When the app asks "what's my rank?", the API reads the bucket
straight off `market_state`, and reads the matching bar off the active `market_reference`.

---

## 6. Placement & the stake ladder — how a new player onboards (Phase 4)

This is the branch in the link flow, and it's where "with history" and "without history" diverge.

- **System 1 (chess, Dota, PUBG — history exists).** The backfill job from step 1 of the spine
  fetches up to the history floor (20/25/20 matches), runs them all through ingest + index, and the
  player lands in a real bucket with high confidence *before they ever wager*. When the app loads
  their markets, the API sees `n ≥ floor` and `index_confidence` high, so their **stake cap is
  removed** — they can bet normally on day one.
- **System 2 (CS2 — no history).** There's nothing to backfill (the share-code chain only goes
  forward). So the API seeds a weak prior (from Steam lifetime stats if present, else the lowest
  bucket) and marks them provisional. They *can* wager from their first match, but when the app asks
  for their markets, the API computes a **stake cap from `index_confidence`**: while the number is
  still climbing, the cap sits at the ladder floor ($5); as confidence rises it unlocks $10, $25,
  then uncapped. This is the smurf defense — a strong player on a fresh account has a low, still-
  climbing index, so their cap stays low exactly while they'd be most dangerous, and by the time it
  opens, the index (via rise-fast + exceptional-result) has caught up to their true skill.

So the frontend does nothing special here — it just displays whatever `stake_cap` the API returns
and disables stakes above it. All the logic is server-side, reading `market_state`.

---

## 7. The wager path — how money enters and a room forms (Phase 5)

This is the one place the **API writes money state**, so it's worth tracing precisely.

When the user confirms a wager, the frontend POSTs `{market, stake}` to the API. The API, in a
single database transaction:

1. Reads `market_state` to confirm the player is placed and allowed (`can_wager`), and that the
   stake is within their cap.
2. **Holds the stake** in the wallet (moves it from balance to an escrow/hold, writing an
   `audit_events` row).
3. Creates a `contest` entry row and pushes the player into the `(game, mode, metric, bucket)`
   **queue** (a Redis structure or a `queued` flag on the entry).

It returns "you're in, waiting for a room." No external call happened; this is all local and fast.

The **worker's matchmaker** then, on its own clock, drains each bucket's queue: when at least `ROOM`
compatible entries are waiting (or the fill window is about to expire with enough of them), it
**forms a room** — writes a `room` row linking the entries — and each entry now points at the one
bar for that bucket. If a bucket can't gather a room before its window closes, the entries are
**refunded and re-queued** (the wallet hold is released, an `audit_events` row written) — never
matched across buckets.

Frontend-wise: after posting the wager, the app **polls** (or subscribes to) a
`/contests/{id}/status` endpoint that walks the entry through `queued → matched → awaiting_result →
settled`, so the user always sees where they are.

---

## 8. Settlement — how a result becomes a payout (Phase 5)

Settlement is the worker recognizing that an *already-ingested* match is the qualifying one for an
open contest. It reuses the ingest path — there's no separate "settlement fetch."

After `matched_at`, the worker watches each room member's ingest stream. When a member's first
finished, gradable match on that metric arrives (through the same `record_match` path from §3), the
worker marks it as the contest's qualifying result. Once every member has a result (or a per-member
deadline passes), it settles in one transaction:

1. For each member, compare their metric value to the room's **one bar** (read from the active
   `market_reference` version — and it records *which* version) → cleared or not.
2. Compute payouts: the pot is `ROOM × stake`, the winners split `pot × (1 − rake)`. **Assert
   `sum(payouts) + rake == pot` to the cent** before committing; integer-cent math; if the assert
   ever fails, abort and refund (fail closed).
3. If **nobody cleared**, refund everyone, rake zero. If a member's result **couldn't be verified**
   (CS2 sidecar down, PUBG 5xx that won't resolve within the window), refund the contest — never
   grade a guessed value.
4. Write one `settlement` row per member (bucket, bar, `reference_version`, result, stake, payout)
   and the matching `audit_events`, and release the wallet holds into balances.

The frontend's status poll flips to `settled` and shows the result and payout. Everything the app
displays about *why* — "you needed 22 kills, you got 19" — comes straight off the `settlement` row,
so it always matches what actually graded.

---

## 9. Disputes & audit — how trust is made reconstructable (Phase 6)

The audit trail isn't a feature bolted on the side; it's a byproduct of every money/placement write
already emitting an `audit_events` row. Disputes just *read* that trail.

**Reconstruction.** There's a `/contests/{id}/explain` endpoint (admin, and a friendlier user
version). Given a contest, it reassembles the whole story purely from stored rows: each player's
index at settlement time, the `reference_version` that was active *then*, that version's cut points
and bar, each result, and the payout arithmetic. The crucial part: it reads the **historical**
reference version off the `settlement` row, not the *current* one — so even after the market has been
re-cut ten times, an old contest still explains itself with the ruler it was actually graded by.

**The dispute lifecycle.** When a user opens a dispute from the result screen, the API creates a
`disputes` row and immediately **snapshots** the relevant `settlement` + `audit_events` (so later
recomputes can't alter the evidence), and optionally places a **hold** that blocks the payout or a
withdrawal touching it. An admin tool walks it through `under_review → resolved_(no_change | refund |
adjust)`; each admin action writes its own `audit_events` row with a reason and `actor='admin'`, so
the trail can't be quietly edited. The frontend shows the dispute state alongside the contest.

The whole point: because Phases 3 and 5 versioned everything, "why did this happen?" is always a
lookup, never a reconstruction from guesswork — which is what lets you win a dispute and keep the
user.

---

## 10. Growing the ladder — how buckets multiply themselves (Phase 7)

This is a **nightly batch job**, `evaluate_market`, run per `(game, mode, metric)`. It's the
auto-scaling brain, and it only ever *proposes* — it never re-cuts live.

Each night it recomputes the three ceilings from live data: **precision** (does the median player
have enough matches to justify narrower buckets?), **stability** (do bootstrapped cut lines stay put
at this population?), and **liquidity** (would every proposed bucket still fill a room?). The largest
K passing all three is the market's eligible bucket count. If that's higher than the current K, it
flags **promote**; lower, **demote**.

Applying the change is a deliberate, separate step — a **season boundary or a migration window** —
because a re-cut moves every line and re-buckets most players at once. The migration: compute the new
`market_reference` version, **freeze settlement** for that market, flip `active` to the new version
atomically, re-bucket everyone under hysteresis, emit the "ladder expanded" event the frontend uses
to show a season change (hide the old number, reveal the new — never a visible rank drop), and write
`audit_events`. Contests settled before the swap keep pointing at the old version, so they still
reconstruct correctly.

The frontend's only involvement is rendering the season/re-cut announcement and the new rank; it
never knows how the lines were drawn.

---

## 11. Monitoring, scale & the ML corpus (Phase 8)

Two ongoing jobs and one dataset.

- **The monitoring rollup** (nightly) computes, per market, the four numbers that drive everything:
  rated players (N), median matches per player (n), per-bucket fill rate, boundary wobble. These
  feed both the promote/demote decision and an ops dashboard where a starving bucket shows up before
  users complain.
- **The anomaly watchdog** watches for indices that jump in ways honest play doesn't (a bought or
  boosted account) and raises a **flag + stake hold for human review** — it never bans or seizes
  automatically, because improvement and cheating look identical to the math and only a human can
  tell them apart. This is detection layered on top; the rating itself stays best-of.
- **The ML corpus** is just `match_stats` read at rest. Because §3 stored *every* field keyed by the
  internal `player_id`, a future job can export point-in-time snapshots (features + outcome,
  pseudonymous) to train the things ML is actually good for here: **learning better index weights**,
  **playstyle hints for suggesting a market**, and **fraud detection**. It is *not* used for the
  bucketing itself, which stays reproducible bands — the corpus is optionality, not a dependency.

Scale holds because of the shape set in §2: the append-only log is the only unbounded table and it
partitions cleanly; every hot-path read hits one small `market_state` row; and all the heavy thinking
(cuts, promotion, monitoring) is batch, not request-time.

---

## 12. The API surface, in one place

So the implementer has the contract in front of them. All are thin — they read/write Postgres and
enqueue; none call a game host inline.

| Method & path | Who calls it | What it does |
| --- | --- | --- |
| `POST /links` | frontend | Verify + create a `game_links` row; enqueue backfill (System 1). Returns link status. |
| `GET /markets` | frontend | For each market the user can play: their bucket, the bucket's bar, their stake cap, payout math. Reads `market_state` + active `market_reference`. |
| `POST /wagers` | frontend | Validate + hold stake + create `contest` entry + enqueue into the bucket queue (one transaction). |
| `GET /contests/{id}/status` | frontend (poll/subscribe) | `queued → matched → awaiting_result → settled` and the outcome. |
| `GET /contests/{id}/explain` | frontend / admin | Reconstruct the grading from stored versioned rows. |
| `POST /disputes` | frontend | Open a dispute; snapshot evidence; optional payout hold. |
| `POST /admin/disputes/{id}/resolve` | admin tool | Resolve (no_change / refund / adjust); writes audited action. |

And the background processes (no HTTP surface, driven by queues + cron):

| Process | Trigger | Does |
| --- | --- | --- |
| Ingest/backfill worker | queue + cursor poll | fetch → adapter → `record_match` → `update_index` → assign bucket |
| Matchmaker | queue drain / fill window | form rooms from bucket queues; refund unfillable |
| Settlement | qualifying match ingested | grade vs bar, enforce money invariant, write settlement + audit, release wallet |
| Reference recompute | nightly cron | draw new versioned cut lines + bars per market |
| `evaluate_market` | nightly cron | the three gates → propose promote/demote |
| Monitoring rollup + anomaly watchdog | nightly cron | the four numbers; flag abnormal index jumps |

---

## 13. How to use this with the phase plan

Pair them: when you start a phase in `IMPLEMENTATION_BUCKETING.md`, read the matching section here
first so you know how that piece plugs into the data flow, then build to the phase's test gate.

| Phase | Read here |
| --- | --- |
| 0 Data model | §2 |
| 1 Ingestion | §3 |
| 2 Index | §4 |
| 3 Buckets | §5 |
| 4 Placement | §6 |
| 5 Matchmaking & settlement | §7, §8 |
| 6 Disputes & audit | §9 |
| 7 Auto-promotion | §10 |
| 8 Monitoring & ML | §11 |

The one sentence to keep in your head while building any of it: **the frontend shows state, the API
serves and guards state, the worker computes state, and Postgres is the only place state actually
lives — so every feature is really "which process writes this row, and which reads it?"**
