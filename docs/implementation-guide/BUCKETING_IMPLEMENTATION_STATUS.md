# Bucketing System — Implementation Status & How to Test It

Companion to `IMPLEMENTATION_BUCKETING.md` (the plan) and
`BUCKETING_TECHNICAL_WALKTHROUGH.md` (how it works). This file records **what is
built so far**, exactly **how to run and see it working**, what is **proven on
any machine** vs. what **needs Postgres (CI)**, and the **remaining phases**.

Everything lives behind the `bucketing_enabled` feature flag, seeded **off** by
migration `0028`. Nothing in `services/bucketing/` can touch money until an admin
turns that flag on, so this can be merged and shipped dark.

Branch: `feat/bucket_system`.

---

## 1. TL;DR — what's done

| Phase | Scope | State | Where |
| --- | --- | --- | --- |
| **0** | Data model + migrations | **Built** (CI-validate) | `migrations/versions/0028_bucketing.py`, `models/bucketing.py` |
| **1** | Idempotent ingestion | **Built** | `services/bucketing/ingestion.py` |
| **2** | Skill index (best-of-40%, Welford) | **Built + fully proven** | `services/bucketing/index.py` |
| **3** | Reference cuts, assignment, hysteresis | **Built + fully proven** | `services/bucketing/reference.py` |
| **4** | Placement + stake ladder | **Core built + proven** | `services/bucketing/placement.py` |
| **5** | Settlement + money invariant | **Core built + proven** | `services/bucketing/settlement.py` |
| **1–3** | Record→index→bucket DB pipeline | **Built** (CI-validate) | `services/bucketing/state.py` |
| 5 | Matchmaking / wager path / worker wiring | **Not yet** | — |
| 6 | Disputes + audit reconstruction | Tables built; workflow **not yet** | `audit_events` in 0028 |
| 7 | Auto promote/demote | **Not yet** | — |
| 8 | Monitoring / ML corpus | **Not yet** | — |

This is **Milestone A ("it records") complete, plus the pure computational cores
of the money phases (4–5) proven ahead of their integration.** The genuinely
hard, correctness-critical, exploit-resistant maths — the anti-sandbag index, the
reproducible buckets, the smurf-safe stake ladder, and the money invariant — is
built and exhaustively unit-tested. The remaining work (Phases 5–8) is mostly
*integration*: wiring these proven pieces into the queue, worker, and admin
surfaces.

---

## 2. Important: the test environment on this machine

This dev box **cannot run the DB-backed suite** — it has no Docker and no
Postgres (the test harness in `tests/conftest.py` builds its schema by running
the real migration chain against a live Postgres on `localhost:5433`).

That splits the tests in two, and it's worth understanding which is which:

- **Pure-function tests** (`pytest -m nodb`) — no database. **These run anywhere,
  and they cover the entire risky core of this system** (the index maths, the
  bucket cuts, the stake ladder, the money invariant). All **57** pass here.
- **DB-backed tests** — need Postgres, so they run **in CI**. **8** of them
  (`test_bucketing_ingestion.py` DB half + `test_bucketing_state.py`) prove the
  idempotency, append-only, and persistence behaviour end to end.

So: the parts where a subtle error would lose money or be exploitable are proven
on any machine; the parts that are "does the SQL do what the model says" are
written to the existing patterns and gated behind CI. **Before enabling the flag
in production, the CI run (with Postgres) must be green** — that is the final
validation of migration `0028` and the `state.py`/`ingestion.py` DB paths, which
could not be executed here.

---

## 3. How to run the tests (and watch it work)

All commands from `apps/api/`. The repo's venv Python is used below.

### 3a. The pure core — runs on this machine, right now

```bash
# Everything that needs no database — the whole bucketing maths core:
.venv/Scripts/python.exe -m pytest tests/test_bucketing_*.py -m nodb -v

# Or just the headline gates:
.venv/Scripts/python.exe -m pytest tests/test_bucketing_index.py -m nodb -v       # anti-sandbag
.venv/Scripts/python.exe -m pytest tests/test_bucketing_settlement.py -m nodb -v  # money invariant
```

Expected: **57 passed**. Notable tests to read:

- `test_throwing_games_costs_nothing_versus_ordinary_bad_games` — the sandbag
  defence, stated precisely: a thrown game is identical to any other sub-median
  game, to the cent.
- `test_money_invariant_holds_across_thousands_of_contests` — 5,000 randomized
  contests, `sum(payouts) + rake == pot` always.
- `test_smurf_extraction_is_bounded_by_the_confidence_cap` — a strong player on a
  fresh account can only stake floor amounts until their index settles.
- `test_cuts_are_deterministic_not_a_random_clusterer` — buckets are reproducible.

### 3b. See it with your own eyes (a 30-second REPL demo)

```bash
.venv/Scripts/python.exe
```

```python
from moneymatch_api.services.bucketing import index as ix, reference as rf

# --- Sandbagging can't move the index ---
strong = ix.rebuild_index([24,26,23,25,27,22,25,24,26,23])  # a good CS2-kills history
print("settled index:", round(strong.index_value, 2))       # ~26
tanked = strong
for _ in range(10):
    tanked = ix.update_index(tanked, 0.0)                    # throw 10 games
print("after throwing 10:", round(tanked.index_value, 2))   # essentially unchanged

# --- Buckets are reproducible bands ---
pop = [g for g in range(10, 40)]                             # a population of indices
ref = rf.build_reference([float(x) for x in pop], k=3)
print("cut points:", [round(c,1) for c in ref.cuts])
print("index 15 -> bucket", ref.bucket_of(15), "| index 35 -> bucket", ref.bucket_of(35))
```

```python
# --- The smurf-safe stake ladder ---
from moneymatch_api.services.bucketing import placement as pl
for conf in (0.0, 0.65, 0.85, 0.95):
    print(f"confidence {conf}: cap =", pl.stake_cap_cents(conf, provisional=False), "cents")
# 0.0 -> 500 ($5), 0.65 -> 1000 ($10), 0.85 -> 2500 ($25), 0.95 -> None (uncapped)
```

### 3c. The full suite (needs Postgres — CI or a local DB)

To run the DB-backed tests, bring up Postgres and point the harness at it:

```bash
# from repo root — starts the postgres:16 service from docker-compose.yml
DB_PORT=5433 docker compose up -d db
# then, from apps/api/:
TEST_DATABASE_URL='postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test' \
  .venv/Scripts/python.exe -m pytest tests/test_bucketing_ingestion.py tests/test_bucketing_state.py -v
```

This exercises migration `0028` (the harness runs the whole chain), the
idempotency constraint, the append-only triggers, and the record→index→bucket
persistence. **This is the step that validates the parts I could not run on the
dev box.**

---

## 4. What each piece does (and the edge cases handled)

### `index.py` — the skill index (Phase 2)

- **Best-of-40% of the last 20 results**, so a thrown game (worst 60%) never
  enters the number → sandbagging is defeated *by construction*, no detector.
- **Welford** running mean/variance — O(1) per match, matches a batch recompute
  (property-tested).
- **Rise-fast / fall-slow**: improvements taken instantly, declines damped to ¼,
  and (with the 12-month floor) a run of bad/thrown games can cost **at most one
  bucket**.
- **Direction-agnostic** via a "goodness" mapping — chess `moves` (lower better)
  and kills/damage/GPM (higher better) share one code path, zero `<`/`>` bugs.
- **Edge cases covered:** metric floor clamps a corrupt `0` (chess Fool's-Mate
  floor of 2); confidence is 0 for n<2 and scale-free across metrics living at
  1.0 vs 400; deterministic byte-for-byte (golden snapshot locked).

### `reference.py` — buckets (Phase 3)

- **Fisher-Jenks (1-D DP) minimum-variance cuts** — *deterministic*, explicitly
  not a seeded k-means, so the same data always yields the same buckets.
- **Quantile fallback** when a market is too small for the variance floor, so no
  bucket is ever born empty.
- **Degenerate-population edge case:** a market where almost everyone shares one
  index collapses K gracefully (a cut is only placed strictly between two
  distinct values) instead of emitting an empty bucket.
- **Assignment** = `searchsorted` (O(log K)); a value exactly on a cut goes up.
- **Hysteresis:** a player only changes bucket after crossing the boundary by 15%
  of a bucket width, and never drops more than one bucket at once → no flapping.
- **Grouping-by-level test:** proves buckets sort by skill level, not by
  erraticness or playstyle.

### `placement.py` — onboarding + stake ladder (Phase 4 core)

- **Confidence-gated ladder** `$5 → $10 → $25 → uncapped`, keyed on *index
  stability*, not game count — the smurf defence. A still-climbing index stays at
  the floor exactly while it's most dangerous.
- **Two systems:** System 1 (history: chess/Dota/PUBG) places from backfill;
  System 2 (no history: CS2) bets from match one but capped.
- **Provisional** markets (< `METRIC_PROVISIONAL_MIN_N` samples) are always
  pinned to the floor stake, even if confidence looks high.

### `settlement.py` — grade-vs-bar + money (Phase 5 core)

- Delegates the pot split to the existing `services/money_math.py`, so
  `sum(payouts) + rake == pot` is enforced in one place and the invariant is
  re-asserted in `SettlementOutcome.__post_init__` (fail-closed: a broken split
  raises).
- **Fail-closed order:** unverifiable data → refund the whole contest; nobody
  clears → refund everyone, zero rake; otherwise clearers split, remainder cents
  to rake. Never grades a guessed value.

### `ingestion.py` + `state.py` — the DB pipeline (Phases 1–3)

- `record_match`: `INSERT … ON CONFLICT DO NOTHING` — concurrency-safe, stores
  **every** field verbatim (the ML corpus), keeps PII out of the log.
- `bucket_mode_for`: the **fail-closed mode gate**. Chess (blitz/rapid) and PUBG
  (official) are ready today; **CS2 and Dota are deliberately gated off** until
  their discriminators exist (see §6).
- `state.record_and_update`: record once → update the index for each metric →
  re-bucket. Skips re-seen matches so the index never double-counts.

---

## 5. The data model (migration 0028)

Five tables, all inert until the flag flips:

- **`match_stats`** — append-only raw log, monthly-**partitioned** by
  `created_at_ms`, idempotency key `(player_id, game, host_match_id,
  created_at_ms)` (the partition column is in the key because Postgres requires
  it; it's deterministic from the match, so re-ingest still conflicts). 36
  monthly partitions (2025–2027) + a DEFAULT safety-net; a Phase-8 job extends
  the window. Append-only trigger rejects UPDATE/DELETE.
- **`market_state`** — one small mutable row per `(player, game, mode, metric)`:
  Welford state, window, index, confidence, bucket, placement. The only table the
  hot path reads per player.
- **`market_reference`** — versioned, seasoned cut points + one bar per bucket; a
  **partial unique index** guarantees exactly one `active` row per market.
- **`settlement`** — append-only audit row (bucket, bar, reference_version,
  result, stake, payout) — the receipt Phase 6 reconstructs from.
- **`audit_events`** — append-only money/placement log (created empty for Phase 6).

---

## 6. Two known gaps to close before enabling CS2 / Dota (flagged, not guessed)

Both are called out in the spec and are enforced fail-closed in code
(`ingestion.MODE_GATE_READY` is `False` for both, so **no CS2 or Dota match is
recorded** until the gap is closed):

1. **CS2 "Competitive only" needs a mode discriminator.** Share codes come from
   Premier, Competitive *and* Wingman. Wingman is trivially excluded (roster ≤ 4),
   but separating Premier vs Competitive requires reading the mode/type from the
   GC resolve payload. Until the CS2 adapter can surface that, CS2 bucketing stays
   off.
2. **Dota "ranked only" needs a `lobby_type` gate.** The adapter reads
   `lobby_type`/`game_mode` but doesn't yet filter to ranked (`lobby_type = 7`,
   excluding Turbo `game_mode = 23`). Add that filter to `_normalize`, then flip
   the gate.

Enabling either is a two-step change: close the adapter gap, then set its
`MODE_GATE_READY` entry to `True`.

---

## 7. Remaining phases (the roadmap from here)

- **Phase 5 — matchmaking + wager path + settlement worker.** Queue a placed
  player into their `(game, mode, metric, bucket)` queue; form rooms; recognise
  the qualifying match through the same ingest path; call `settlement.settle_room`;
  write the `settlement` row and release wallet holds. The money maths is already
  proven; this is wiring it to the wallet + worker.
- **Phase 6 — disputes + reconstruction.** `audit_events` exists; add the
  `/contests/{id}/explain` reconstruction (reads the *historical*
  reference_version off the settlement row) and the dispute lifecycle + holds.
- **Phase 7 — auto promote/demote.** Nightly `evaluate_market` (precision /
  stability / liquidity gates) proposes K; a controlled, frozen, versioned re-cut
  applies it via `state.activate_reference` (already built).
- **Phase 8 — monitoring + ML corpus.** The four per-market numbers, partition
  rollover, the anomaly watchdog (flag + hold, never auto-ban), and the
  pseudonymous corpus export.

---

## 8. Commits on this branch

1. `feat(bucketing): pure computational core` — index, reference, placement,
   settlement, markets (+ 53 pure tests).
2. `feat(bucketing): data model (Phase 0) + idempotent ingestion (Phase 1)` —
   migration 0028, models, ingestion, the `bucketing_enabled` flag.
3. `feat(bucketing): record->index->bucket persistence pipeline` — `state.py` +
   integration tests.

Each was committed with the full `nodb` suite green (399 passing, no regressions).
