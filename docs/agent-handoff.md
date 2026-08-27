# Technical agent handoff

The orientation for anyone — human or agent — about to change the backend. It is
the **technical** counterpart to the product/marketing handoff: this document is
about money correctness and system invariants, not roadmap or positioning.

Read this before touching `apps/api`. For workflow (branch, commit, test, review)
see [`../CONTRIBUTING.md`](../CONTRIBUTING.md). To add a game, see
[`adding-a-game.md`](adding-a-game.md); to add a contest type, see
[`adding-a-market-kind.md`](adding-a-market-kind.md).

## The one thing to internalize

The core money infrastructure is **game-agnostic**. Games plug in behind a single
interface (`adapters/base.py::GameAdapter`); the engines, the worker, and the
money math never see host-specific JSON. Keep it that way. New game logic goes
behind the adapter, not into the engines. (The one deliberate exception is
documented under [Intentional seams](#intentional-seams-document-dont-re-architect).)

## Where to start reading (in order)

1. `config.py` — every environment variable, and what fails fast without it.
2. `constants.py` — the tunable numbers (room sizes, windows, caps, metrics,
   labels). One place, heavily commented.
3. `adapters/base.py` — the `GameAdapter` ABC and the shared value types
   (`NormGame`, `TelemetrySample`, `GameFilters`). The whole game-agnostic
   boundary is here.
4. `services/markets.py` — market **kinds** (`win_h2h`, `win_next`, `stat_race`)
   and the `MarketDef` catalog.
5. `services/money_math.py` — integer-cents payout/split/rake arithmetic. The
   money is computed here and nowhere else.
6. The three entry engines: `services/matchmaking.py` (H2H), `services/pool_engine.py`
   (solo pools), `services/tournament_engine.py` (fields). Escrow happens at
   match confirm / room formation / field formation.
7. `services/grading.py` + `services/match_lifecycle.py` — turn a host result
   into a settled outcome and a ledger movement.
8. `workers/settlement_worker.py` — the out-of-process loop that grades due
   contests, settles or refunds, and reconciles.
9. `services/reconciliation_service.py` — the post-settle book check that can
   halt the worker.

## The money path (end to end)

1. **Link** a game account (`link_account`) → the adapter verifies the host
   account and returns a profile; metric models bootstrap from history.
2. **Enter** a contest. The engine validates eligibility, freezes a baseline
   snapshot, and takes **escrow** — at match confirm (H2H), room formation
   (pool), or field formation (tournament). No escrow is held while merely
   waiting in a queue.
3. **Play** on the host. Nothing is self-reported; the server fetches results.
4. **Settle** in the worker: `grading.grade` reads the result through the
   adapter, `money_math` computes the split/payout in integer cents,
   `match_lifecycle` writes the ledger movement and the terminal state — each
   unit of work in its own transaction, claimed with `FOR UPDATE SKIP LOCKED`.
5. **Reconcile.** After settling, the book is checked; a breach halts settlement
   (see below). Unverifiable entrants (no qualifying result the server can read)
   are **refunded**, never guessed at.

## Invariants that must never break

A change that violates any of these is wrong even if the tests pass — add the
test if it is missing.

1. **Integer cents only on the money path.** No `float` ever represents money.
   Enforced by `test_no_floats_in_money_path.py`.
2. **Money math is conserved.** Payouts + refunds + rake equal the pot; no cents
   are created or destroyed by rounding. Enforced by
   `test_money_invariants_property.py` (property-based).
3. **Escrow precedes play.** A player's stake is held before they can affect an
   outcome. No path settles a contest whose stakes were never escrowed.
4. **Idempotent, race-safe settlement.** Work is claimed with `FOR UPDATE SKIP
   LOCKED` and every state transition is idempotent, so concurrent workers (or a
   crash between claim and commit) never double-settle. This is what makes the
   in-process worker mode safe (`test_in_process_worker.py`).
5. **Unverifiable → refund, never guess.** A contestant with no server-readable
   qualifying result is refunded. Only fabricated demo opponents are ever graded
   without a lookup, and only for the demo account.
6. **Fail closed.** On a reconciliation breach the worker pauses settlement for
   everyone rather than committing against a broken book (see below). The geo
   fence refuses to boot prod without a seeded floor.
7. **The core stays game-agnostic.** Host specifics live behind `GameAdapter`.
8. **No demo/dev path in production.** `demo_login`, `e2e_auth`,
   `demo_simulate`, and the practice-opponent scaffolding are guarded off in
   prod and must stay that way.

## What each test proves (the safety net)

The suite is the specification of the invariants above. When one fails, it is
telling you which invariant your change broke.

- **Money conservation** — `test_money_invariants_property.py` (property-based
  split/rake/refund conservation), `test_no_floats_in_money_path.py` (no floats).
- **Bar placement is stable and honest** — `test_bar_golden.py` (golden
  snapshots of quoted bars), `test_bar_direction.py`, `test_bar_realism.py`.
- **Numerics reconcile** — `test_numerics_reconciliation.py` (the scipy path
  agrees with the reference).
- **Engines settle correctly** — `test_pool_engine.py`,
  `test_pool_clearing_opponent.py` (clearers split, missers forfeit),
  `test_challenge_service.py`, `test_disputes.py`.
- **Anti-abuse holds** — `test_sandbagging.py`, `test_caps.py`,
  `test_idor_matrix.py`, `test_admin_authz.py`, `test_kyc_policy.py`.
- **Adapters honor the contract** — `test_adapter_registry.py`,
  `test_chess_lichess_adapter.py`, `test_dota2_opendota_adapter.py`,
  `test_cs2_*` (intake, prior, chain, short matches).
- **Config fails fast** — `test_config.py`, `test_gc_sidecar_url.py`,
  `test_geo_service.py`.
- **Migrations build the schema** — `test_migration_seed_parity.py` (the test DB
  is built by running migrations, not `create_all`, so drift is caught).
- **Docs stay honest** — `test_docs_do_not_drift.py` (comments/docs that cite
  code are checked against the code).

## Intentional seams (document, don't re-architect)

Two things look like smells but are deliberate. They are documented here so a
future change is a decision, not an accident.

### 1. `ReconciliationError` halts settlement globally (fail-closed)

When the post-settle reconciliation in `settlement_worker` detects a breach, it
raises `ReconciliationError`, sets the `settlement_paused` kill switch, and stops
the loop. **This pauses settlement for _all_ games, not just the one that
breached.** That is intentional: a book that does not reconcile is evidence the
money math is wrong somewhere, and continuing to pay out against it is the one
thing worse than a delayed settlement. `/health` and the admin reconciliation
view redden so an operator sees it immediately. Do not "improve" this into a
per-game pause — a breach anywhere means the ledger is untrustworthy everywhere.

### 2. `_sync_share_chains()` — the one non-game-agnostic call in the worker

`settlement_worker._sync_share_chains()` collects new CS2 matches (Valve's
share-code chain) at the top of each cycle. It is CS2-specific — the single place
the otherwise game-agnostic worker names a game. **Left as-is on purpose.**
Generalizing it into an adapter `pre_cycle_hook()` only pays off once a second
title needs a similar periodic intake loop, and the current direction is to stop
spending on CS2. Revisit only when a new game actually needs it; until then a
speculative abstraction would carry cost for no second caller. It already fails
soft (a slow Valve never blocks settlement).
