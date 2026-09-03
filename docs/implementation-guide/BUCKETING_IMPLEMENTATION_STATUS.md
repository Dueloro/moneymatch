# Bucketing System — What's Built & How to Test It

All 8 phases are implemented and tested against a real Postgres. Everything is
behind the `bucketing_enabled` flag (seeded **off** by migration 0028), so it
ships without touching live money. Branch: `feat/bucket_system`.

**One-command check (needs the local Postgres on port 5433):**

```bash
cd apps/api
TEST_DATABASE_URL='postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test' \
  .venv/Scripts/python.exe -m pytest tests/test_bucketing_*.py -q
```

Expected: **97 passed**. If you see that, the whole layer works. Any `F` (fail)
names the exact behaviour that broke and the file:line — that's how you know
something's wrong.

The pure-maths half needs no database and runs anywhere:

```bash
.venv/Scripts/python.exe -m pytest tests/test_bucketing_*.py -m nodb -q   # ~61 tests
```

---

## What each piece is, how it works, and the one test that proves it

| # | Piece | How it works (one line) | Prove it | Passing means… | Failing would mean… |
|---|-------|------------------------|----------|----------------|---------------------|
| 2 | **Skill index** (`index.py`) | Your rating = mean of your *best 40%* of the last 20 games, rises fast / falls slow | `test_throwing_games_costs_nothing…` | Throwing games can't lower your rank (sandbag-proof) | A thrown game moved the index → farmable ranks |
| 3 | **Buckets** (`reference.py`) | Cut the skill line into tiers with a *deterministic* algorithm; a margin stops boundary flip-flop | `test_cuts_are_deterministic…`, `test_small_oscillation_does_not_change_bucket` | Same data → same tiers, every time; no flapping | Random tiers, or players bouncing between tiers each game |
| 4 | **Stake ladder** (`placement.py`) | New players are stake-capped ($5→$10→$25→∞) until their rating *settles* | `test_smurf_extraction_is_bounded…` | A smurf can only win a few $ before being caught up to | A smurf could bet big and clean out honest players |
| 5 | **Wager + settle** (`contest.py`) | Bet → matched into a room → graded vs one bar → money moves | `test_settlement_conserves_money…`, `test_money_invariant_holds…` (5,000 random cases) | `payouts + rake == pot` to the cent, always | Money created or lost in a payout |
| 5 | **Fail-closed** (`contest.py`) | Bad/missing result → refund everyone, never guess | `test_unverifiable_result_voids…`, `test_nobody_clears_refunds…` | A broken feed refunds instead of grading a guess | A wager settled on made-up data |
| 6 | **Reconstruction** (`disputes.py`) | Explain any old contest from stored rows, using the tier table *from when it settled* | `test_reconstruction_uses_the_historical_reference_after_a_recut` | An old bet still explains itself after tiers change | "Why did I lose?" gives the wrong (current) answer |
| 6 | **Clawback** (`disputes.py`) | On confirmed cheating: void the game, refund honest players **from the cheater's pocket** | `test_clawback_refunds_honest_players_from_the_cheaters_pocket` | Honest players made whole; cheater forfeits; platform doesn't pay | Honest players left short, or the house eats the cost |
| 7 | **Grow tiers** (`promotion.py`) | Nightly job adds/removes tiers via 3 gates (precision, stability, liquidity) | `test_low_liquidity_caps_k_and_names_the_gate` | Tiers only split when there's enough data + players | Tiers split on noise → unfair matches |
| 8 | **Monitoring/ML** (`monitoring.py`) | Health numbers, cheat-flag (→ review, never auto-ban), pseudonymous data export | `test_anomaly_flags_elite_index…`, `test_corpus_export_is_pseudonymous…` | Suspicious accounts flagged with **zero** money moved; export has no personal info | An account auto-banned, or PII leaked into the dataset |

### The clawback, specifically (what you asked for)

`resolve_with_clawback(dispute_id, fault_player_ids, admin=…)`:
- **`explain_room(room_id)`** gives the admin the evidence — every player's wager,
  their bar, their actual result, and their **full recorded match stats** — to
  decide who was unfair. (Fault is an admin call, aided by the Phase-8 anomaly
  flags; the system lays out the log, it doesn't accuse on its own.)
- The refunds to honest players are paid **from what's recovered from the
  cheater**. The platform only covers a shortfall if the cheater's wallet is
  already empty, so a victim is never left short. Every cent (recovered /
  refunded / backstop) is written to `audit_events`.

---

## The 4 bugs a real database caught (all fixed)

1. **First-game crash** — a new player's stat row was blank in memory; the first
   match crashed. Fixed by seeding the zero-state explicitly.
2. **Wallet rejected bets** — the ledger only allowed known transaction tags;
   added the two bucketing tags (migration 0030).
3. **Refunding money already gone** — a post-settlement refund tried to pull from
   an empty escrow; now pays from the correct source (and, per your request, a
   *cheating* refund pulls from the cheater — the clawback above).
4. **Nightly job hung at scale** — the tier-growth check re-ran an expensive
   calculation on the whole population; now runs on a small sample.

---

## Known gaps (deliberate, fail-closed)

CS2 and Dota are switched **off** in `ingestion.py` (`MODE_GATE_READY = False`) —
no match is recorded for them until CS2 can tell Competitive from Premier/Wingman
and Dota can filter to ranked-only. Chess and PUBG work today.

---

## Before turning the flag on: what's left ("wiring")

The engine is done and tested. What remains is **connecting these already-tested
functions to the running app** — no new rating/settlement logic, just plumbing:

1. **Background jobs** call the services on a clock: the settlement worker calls
   `state.record_and_update` when a match arrives; the matchmaker calls
   `contest.form_room` / `settle_room` / `expire_unfilled`; the nightly job calls
   `promotion.evaluate_market` + `monitoring.*`.
2. **API endpoints** (thin) let the app reach them: `GET /markets`, `POST /wagers`,
   `GET /contests/{id}/status`, `GET /contests/{id}/explain`, `POST /disputes`,
   and the admin resolve/clawback.
3. **Freeze flag** around a tier re-cut (mirrors the existing `settlement_paused`
   flag), and route `monitoring.detect_anomalies` output to the admin risk queue.
4. Turn `bucketing_enabled` on behind a staged rollout.
