# Bucketing System — Implementation Status & How to Test It

Companion to `IMPLEMENTATION_BUCKETING.md` (the plan) and
`BUCKETING_TECHNICAL_WALKTHROUGH.md` (how it works). This file records **what is
built**, exactly **how to run and see it working**, and what remains.

**All eight phases (0–8) are now implemented and tested end to end.** Everything
lives behind the `bucketing_enabled` feature flag, seeded **off** by migration
`0028`, so it ships dark and moves no money until an admin turns it on.

Branch: `feat/bucket_system`.

---

## 1. Status at a glance

| Phase | Scope | State | Where |
| --- | --- | --- | --- |
| **0** | Data model + migrations | **Built + validated on Postgres** | `migrations/0028–0031`, `models/bucketing.py`, `models/bucket_contest.py`, `models/bucket_dispute.py` |
| **1** | Idempotent ingestion | **Built + tested** | `services/bucketing/ingestion.py` |
| **2** | Skill index (best-of-40%, Welford) | **Built + fully proven** | `services/bucketing/index.py` |
| **3** | Reference cuts, assignment, hysteresis | **Built + fully proven** | `services/bucketing/reference.py` |
| **4** | Placement + stake ladder | **Built + proven** | `services/bucketing/placement.py` |
| **5** | Matchmaking + settlement + money invariant | **Built + tested (real wallet)** | `services/bucketing/contest.py`, `settlement.py` |
| **6** | Disputes + audit reconstruction | **Built + tested** | `services/bucketing/disputes.py` |
| **7** | Auto promote/demote | **Built + tested** | `services/bucketing/promotion.py` |
| **8** | Monitoring + anomaly + ML corpus | **Built + tested** | `services/bucketing/monitoring.py` |

~**94 tests** cover the layer: ~61 pure-function (`nodb`, run anywhere) and ~33
DB-backed (run against Postgres). Everything passes.

---

## 2. Test environment — now with a real Postgres

Earlier this box had no database, so only the pure maths could run here. That is
resolved: a **portable PostgreSQL 16** was fetched and a local cluster stood up on
port **5433**, so the *entire* suite — migrations included — now runs locally, and
did. Standing that up **caught four real production bugs** that pure tests never
would have (see §6).

- **Pure-function tests** (`pytest -m nodb`) — no DB; the whole skill/bucket/
  ladder/money maths. Fast, run anywhere.
- **DB-backed tests** — build the schema from the real migration chain and
  exercise ingestion, settlement against the wallet, disputes, re-cuts, and the
  corpus export.

---

## 3. How to run the tests (and watch it work)

All commands from `apps/api/`.

### 3a. The pure core — runs on any machine

```bash
.venv/Scripts/python.exe -m pytest tests/test_bucketing_*.py -m nodb -q
```

Notable gates:
- `test_throwing_games_costs_nothing_versus_ordinary_bad_games` — the anti-sandbag
  property, stated exactly.
- `test_money_invariant_holds_across_thousands_of_contests` — 5,000 randomized
  contests, `sum(payouts)+rake == pot`.
- `test_smurf_extraction_is_bounded_by_the_confidence_cap` — bounded smurf damage.
- `test_low_liquidity_caps_k_and_names_the_gate` — the promote/demote gates.

### 3b. The full suite — against Postgres

If a database is available (CI, or the local portable cluster on 5433):

```bash
TEST_DATABASE_URL='postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test' \
  .venv/Scripts/python.exe -m pytest tests/test_bucketing_*.py -q
```

This runs migrations `0028`–`0031`, then the end-to-end wager→room→settlement
money flow, disputes/reconstruction, re-cuts, and the corpus export.

To stand up the portable cluster (one-time), the binaries are already extracted
under the session scratchpad; `initdb` a data dir, `pg_ctl … -o "-p 5433" start`,
and `createdb moneymatch_test`. (Any Postgres 16 works — this is just what was
used here.)

### 3c. See it with your own eyes (REPL)

```python
from moneymatch_api.services.bucketing import index as ix, reference as rf, placement as pl
strong = ix.rebuild_index([24,26,23,25,27,22,25,24,26,23])
print(round(strong.index_value,2))                     # ~26
t = strong
for _ in range(10): t = ix.update_index(t, 0.0)        # throw 10 games
print(round(t.index_value,2))                          # basically unchanged
for c in (0.0,0.65,0.85,0.95):
    print(c, pl.stake_cap_cents(c, provisional=False))  # 500,1000,2500,None
```

---

## 4. The full flow, and where each phase lives

```
link → ingest (record_match, idempotent, stores every field)          Phase 1
     → update_market_state (best-of-40% index + bucket + hysteresis)   Phases 2–3
     → place (System 1/2 + confidence-gated stake ladder)              Phase 4
     → enter_wager (validate cap, hold stake) → form_room (one bar)    Phase 5
     → settle_room (grade vs bar, move money, money invariant)         Phase 5
     → explain_contest / disputes (reconstruct from versioned rows)    Phase 6
overnight:
     → evaluate_market (3 gates) → apply_recut (versioned, re-bucket)  Phase 7
     → market_health / detect_anomalies / export_corpus                Phase 8
```

Money moves **only** through the existing `wallet_service` (escrow hold →
release/payout/refund + rake), and the invariant `sum(payouts)+rake == pot` is
asserted before any settlement commits. Bad or missing data **fails closed** to a
refund — a guessed value never grades.

---

## 5. The data model (migrations 0028–0031)

- **`match_stats`** — append-only, monthly-partitioned raw log; idempotency key
  `(player_id, game, host_match_id, created_at_ms)`.
- **`market_state`** — one mutable row per `(player, game, mode, metric)`:
  Welford state, window, index, confidence, bucket, placement.
- **`market_reference`** — versioned cut points + one bar per bucket; a partial
  unique index enforces exactly one active version per market.
- **`settlement`** / **`audit_events`** — append-only receipts of every money/
  placement change.
- **`bucket_room`** / **`bucket_contest`** — the wager path; a partial unique
  index enforces one open wager per market per player.
- **`bucket_dispute`** — the dispute lifecycle with an immutable evidence snapshot.
- Migration `0030` extends the ledger `ref_type` whitelist for bucketing legs.

---

## 6. Bugs the real database caught (that pure tests could not)

Standing up Postgres paid for itself immediately:

1. **First-match `None` crash.** A freshly-created `market_state` row had `None`
   for its numeric columns (server defaults apply on INSERT, not to the in-memory
   object), so the very first match for every new player crashed the index update.
2. **Ledger `ref_type` rejection.** Bucketing money legs were blocked by the
   `ck_ledger_ref_type` CHECK constraint — fixed by migration `0030`.
3. **Post-settlement dispute refund.** A dispute refund tried to move escrow that
   settlement had already consumed; corrected to a platform-funded `credit`.
4. **Promotion job would hang at scale.** The stability bootstrap re-ran the
   O(k·n²) cut maths on the full population; on ~900 points it never returned.
   Fixed with a bounded, seeded downsample before it could reach production.

There was also one **test-isolation** fix: `market_reference` has no user FK, so
the conftest now truncates it explicitly between tests.

---

## 7. Two known gaps to close before enabling CS2 / Dota

Both are enforced **fail-closed** (`ingestion.MODE_GATE_READY = False`), so no
CS2 or Dota match is recorded until:

1. **CS2** gets a Competitive-vs-Premier/Wingman discriminator from the GC resolve
   payload, and
2. **Dota** gets a `lobby_type = ranked` gate in its adapter `_normalize`.

Chess (blitz/rapid) and PUBG (official) are ready today. Enabling a gated game is
a two-step change: close the adapter gap, then flip its `MODE_GATE_READY` entry.

---

## 8. What's left before turning the flag on in production

The engine is complete and tested; the remaining work is **wiring + ops**, not new
algorithms:

- **Worker/cron wiring.** Call `record_and_update` from the settlement poller,
  `form_room`/`settle_room`/`expire_unfilled` on the matchmaker/settlement clocks,
  and `evaluate_market`/`market_health`/`detect_anomalies` from the nightly job.
- **API surface.** Thin endpoints for `GET /markets`, `POST /wagers`,
  `GET /contests/{id}/status`, `GET /contests/{id}/explain`, `POST /disputes`, and
  the admin resolve — each just calls the services here.
- **Settlement freeze around a re-cut.** A market-scoped pause flag the re-cut
  toggles (the mechanism mirrors the existing `settlement_paused` flag).
- **Anomaly → risk queue.** `detect_anomalies` writes an audit event today; wire it
  to the existing risk-flag/admin surface for the stake hold + review.
- **Run the full CI suite with Postgres** and enable the flag behind a staged
  rollout.

---

## 9. Commits on this branch

1. Pure computational core (index, reference, placement, settlement, markets).
2. Data model (Phase 0) + idempotent ingestion (Phase 1).
3. record→index→bucket persistence pipeline.
4. Phase 5 — wager path, room formation & settlement (money invariant).
5. Phase 6 — disputes & audit reconstruction.
6. Phase 7 — auto promote/demote.
7. Phase 8 — monitoring, anomaly watchdog & ML corpus.

Each was committed with its tests green.
