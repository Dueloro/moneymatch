# Implementation Phases — Status & How to Test

What's built against `IMPLEMENTATION_PHASES.md` (peer-to-peer 1v1 + tournaments,
**no bar** — bucketing is matchmaking-only). Branch: `feat/bucket_system`.

**Important framing:** most of this plan was already built across the codebase and
the earlier bucketing work. This session added the **genuinely new** pieces the
plan introduces on top: the **win-streak matchmaking ladder** (Phase 4), the
**best-of-N-in-window tournament scoring** (Phase 5, different from the existing
first-N engine), and the **collusion co-entry guard** (Phase 6). Everything is
behind `bucketing_enabled` (seeded off), so nothing touches live play yet.

> **One thing to know:** this plan says *bucketing decides who you play, never
> what you wager* (no bar). The bar-based settlement from the earlier bucketing
> work is a **separate** path; this plan's money model is pure peer-to-peer —
> 1v1 higher-stat-wins-pot and tournament top-3 split, both rake-off-the-top.

---

## One-command check (needs the local Postgres on port 5433)

```bash
cd apps/api
TEST_DATABASE_URL='postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test' \
  .venv/Scripts/python.exe -m pytest tests/test_streak_ladder.py tests/test_tournament_scoring.py \
    tests/test_collusion.py tests/test_streak_service.py -q
```

Expected: **37 passed** (33 pure + 4 DB). The pure ones also run with no database
via `-m nodb`.

---

## Phase-by-phase: what implements it, and the test that proves it

| Phase | Status | Where it lives | Prove it |
|---|---|---|---|
| **0 Foundations** (registry, clock, worker, migrations) | **Exists** | `constants.py` game/metric registry, `clock.py`, `workers/`, alembic chain | `test_migration_seed_parity`, `test_in_process_worker` |
| **1 Idempotent per-game stat capture** | **Exists** (bucketing) | `bucketing/ingestion.py` (`match_stats`, `ON CONFLICT DO NOTHING`, full raw `metrics`), mode gate | `test_bucketing_ingestion` (re-ingest = 1 row; wrong mode skipped) |
| **2 Skill index + buckets (sandbag-proof)** | **Exists** (bucketing) | `bucketing/index.py` (best-of-40%, rise-fast/fall-slow, peak floor, confidence), `bucketing/reference.py` (cuts + hysteresis) | `test_bucketing_index`, `test_bucketing_reference` |
| **3 Wallet + double-entry ledger + escrow + rake** | **Exists** | `services/wallet_service.py`, `services/money_math.py` (integer-gem, invariant) | `test_wallet_service`, `test_money_invariants_property` |
| **4 1v1 + streak ladder + fish protection** | **1v1 exists; streak ladder + caps NEW** | pairing `services/pairing.py`; **`services/streak_ladder.py`** + **`streak_service.py`** (climb/reset/target); stake caps `bucketing/placement.py` | **`test_streak_ladder`**, **`test_streak_service`** |
| **5 Best-of-N-in-window tournament, top-3 60/25/15** | **NEW scoring** (existing engine is first-N) | **`services/tournament_scoring.py`** (window cutoff, max/avg/best-k knob, deterministic tie-break, 60/25/15, underfill void) | **`test_tournament_scoring`** |
| **6 Smurf/sandbag/collusion flags** | **Mostly exists; collusion guard NEW** | smurf/sandbag structural (Phase 2/4) + `sandbagging_service`, `risk_detectors`, `bucketing/monitoring.detect_anomalies`; **`services/collusion.py`** (co-entry block) | **`test_collusion`**, `test_sandbagging`, `test_risk_detectors` |
| **7 Disputes, clawback, admin audit** | **Exists** (bucketing) | `bucketing/disputes.py` (`explain_contest` reconstruction, `resolve_with_clawback` — refund honest players from the cheater), `audit_events` append-only | `test_bucketing_disputes` |
| **8 Polish & hardening** | **Partial** | live snapshots, notifications, geo/age gates, monitoring rollup exist; full live playtest is the launch step | `test_bucketing_monitoring`, existing endpoint suites |

---

## The three new pieces this session, in plain terms

### Phase 4 — the win-streak ladder (`streak_ladder.py` + `streak_service.py`)
- **Win → your next match aims a rung higher; win again → higher still** (capped).
  **Lose → reset to your own level.** Draw/void → unchanged.
- The offset is always **≥ 0**, so you're **never matched above yourself unless
  you climbed there by winning**, and a loss can't push you *below* your level —
  that's the fish protection, and it's also the anti-smurf (a smurf's wins rocket
  their matchmaking target up and out of the beginner pool fast).
- It shifts **who you play, never what you wager** — matchmaking only.
- **How to see it:** `test_streak_ladder::test_three_win_streak_climbs_monotonically_then_a_loss_resets`
  and `test_streak_service::test_matchmaking_target_climbs_with_streak`. A pass
  means the climb/reset works and is direction-correct; a fail would show the
  target not moving on a win, or moving below your level on a loss.

### Phase 5 — best-of-N-in-window tournament (`tournament_scoring.py`)
- Your score = your **best game that *finished* inside the 3-hour window** (a game
  still in progress at the cutoff **does not count** — enforced by the timestamp
  filter). Aggregation is a **config knob** (`max`/`average`/`best_k`) so the
  skill-vs-chance posture is tunable per state without a rewrite.
- Top-3 split **60/25/15 of (pot − rake)**, exact to the gem; ties break
  **deterministically** (earliest-to-reach, then fewer games); **underfill → void
  + refund everyone** (never top up a prize).
- **How to see it:** `test_tournament_scoring` — the cutoff-excludes-in-progress
  test, the 60/25/15 reconciliation, and the 2000-tournament money-invariant. A
  pass means money is conserved to the gem and the cutoff/tie rules hold; a fail
  would break `sum(payouts)+rake == pot` or count a late game.

### Phase 6 — collusion co-entry guard (`collusion.py`)
- Two accounts that **share a device / IP / payment signal cannot co-enter** the
  same contest (blocked + flag). Unknown signals never match, so a legitimate
  player is never blocked for lacking a fingerprint.
- **How to see it:** `test_collusion` — shared-device blocks, distinct players
  co-enter, kinds don't cross-collide.

---

## What's left before real users (ops + integration, not new logic)

- **Wire the streak hook into 1v1 settlement:** call `streak_service.apply_result`
  when a duel settles, and center pairing on `matchmaking_target_for`. (The maths
  and persistence are done + tested; this is one call in the settlement path.)
- **Capture fingerprints** (device/IP/payment) at entry and pass them to
  `collusion.can_co_enter` — the decision is done; the capture is an integration.
- **Choose the tournament path:** either point the tournament worker at
  `tournament_scoring.settle_tournament` (best-of-N) or keep the existing first-N
  engine — the plan's `max` model is now available as a drop-in.
- **Gems→real-money** is a later config + compliance step (the ledger is already
  currency-agnostic).
- Run the **full suite in CI** with a stable Postgres before flipping the flag.

---

## Known gaps carried over (deliberate, fail-closed)

CS2 and Dota stay **off** in `bucketing/ingestion.MODE_GATE_READY` until CS2 can
tell Competitive from Premier/Wingman and Dota can filter to ranked-only. Chess
and PUBG are ready. (Chess is the cleanest 1v1-native game, per the plan.)
