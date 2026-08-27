# Data Model Reference

A living map of the database — the tables, what they hold, and the two invariants
the schema exists to protect. This replaces the throwaway point-in-time snapshot;
for the authoritative definition always read the SQLAlchemy models in
`apps/api/src/moneymatch_api/models/` and the Alembic revisions in
`apps/api/migrations/versions/` (forward-only; 0001 → 0017 today, latest
`0017_chat`).

**The two things the schema protects:**
1. `sum(payouts) + rake == sum(entries)` on every settlement — enforced by the
   ledger, asserted by reconciliation.
2. The server owns every number — clients reference rows by id; amounts live only
   here.

---

## Money (the core — `models/wallet.py`)

- **`wallets`** — one per user. Holds **cached** balances only: `available_cents`,
  escrow, and lifetime-net. A `CheckConstraint` keeps `available_cents >= 0`.
  These are derived from the ledger and written inside the same transaction as the
  rows that move them — never updated on their own.
- **`ledger_entries`** — the **append-only** source of truth. Each row is signed
  (`amount_cents` applies to available, `escrow_delta_cents` to escrow) and
  carries the running `available` balance after it applied (so any statement is a
  range query). Entry types: `demo_deposit`, `demo_withdrawal`, `escrow_hold`,
  `escrow_release`, `payout`, `rake`, `refund`, `adjustment`. Each row references
  what caused it via a ref type: `match`, `solo_pool`, `tournament`, `admin`,
  `demo_rail`.
- **`platform_ledger`** — the wallet-less chart of accounts for the house side:
  `platform:rake` (revenue) and `platform:promo` (the funding source for demo
  signup grants — the $1,000 grant is a real ledger row, not a magic balance).
- **`limits`** — per-user staking limits (daily loss/entry/deposit caps, max
  concurrent contests), defaulted from the single Phase-1 caps table so they can't
  drift. Raises apply lazily via `pending_limits` + `pending_effective_at` (a
  protective cap can be lowered instantly but raised only after a cool-down).

## Identity (`models/user.py`, `models/linked_account.py`)

- **`users`** — one per Supabase auth id. Also holds `kyc_status`
  (`none|pending|verified|failed`, default `none`) and the friend code.
  - **`active_games`** (JSONB list) — the player's "play set", the **single
    source of truth** for which games render anywhere in the app (tabs, cards,
    pickers). Distinct from linking: a game is selected first, then linked.
    Empty is treated as **Chess-only** (fail-closed) by the client, and migration
    `0026` backfilled existing users to their linked games (else Chess).
  - **`dismissed_checklists`** (JSONB list) — games whose Play-tab onboarding
    checklist the player dismissed. Kept a subset of `active_games`: removing a
    game drops its dismissal, so re-adding shows the checklist again.
- **`linked_accounts`** — a user's bound host accounts. Uniqueness is a **partial**
  index on `status <> 'unbound'`, so a **soft-unbind** (`status='unbound'`) frees
  the slot for a rebind while keeping the row for FK history.
- **`metric_models`** — per `(user, game, metric)` skill model (μ/σ) that personal
  bars and forecasts read; bootstrapped from real match history.
- **`raw_payloads`** — retained raw host JSON (link/profile/settlement evidence)
  for audit replay; grading records back-reference it.

## Contests

- **Head-to-head** (`models/play.py`): **`queue_tickets`** (the DB-backed
  matchmaking queue, claimed with `FOR UPDATE SKIP LOCKED`), **`matches`**, and
  **`match_players`** (FK to `linked_accounts`, `ondelete=RESTRICT` — the reason
  binds soft-unbind).
- **Solo pools** (`models/pools.py`): **`solo_pools`** + **`solo_entries`** —
  personal-bar rooms with averaged room bars.
- **Tournaments** (`models/tournaments.py`): **`tournaments`** +
  **`tournament_entries`** — matchmade stat tournaments, top-3 split.

All three settle through the same worker and obey the same money invariant; each
has an explicit state machine (see `services/match_states.py` and the engines).

## Social & messaging (`models/social.py`, `models/chat.py`, `models/notification.py`, `models/push.py`)

- **`friendships`**, **`challenges`** (single-use invite tokens).
- **`conversations`**, **`conversation_members`**, **`messages`** — the Inbox
  (friend DMs + the pinned Support thread + invite cards).
- **`notifications`** (with a `channel_sent` seam for future email/push) and
  **`push_subscriptions`**.

## Risk, ops & audit (`models/risk.py`, `models/dispute.py`, `models/feature_flag.py`, `models/admin_audit.py`, `models/live.py`)

- **`risk_flags`** — persisted detector output (`kind` includes sandbagging,
  `win_streak`); informational flags never block play, gating flags do.
- **`disputes`** — polymorphic (ref + reason + state) operator-mediated review
  queue (migration `0016`). Self-report is deliberately absent.
- **`feature_flags`** — kill switches read by the API (`queue_paused`,
  `settlement_paused`, per-game `game:<id>`, `geo_config`), flippable without a
  deploy.
- **`admin_audit`** — every admin mutation writes a row here.
- **`live_snapshots`** — best-effort mid-game state for the Activity live view.

---

## Working with the schema

- **Migrations are forward-only.** Every schema change ships its Alembic revision
  in the same PR. Generate with the API's alembic env; apply with `make migrate`.
- **Never bypass the ledger.** Money moves only by inserting `ledger_entries` (and
  updating the cached `wallets` balance in the same transaction) through the wallet
  service. Reconciliation reads straight from the ledger to assert the invariant.
- **The models are the source of truth for shapes**; this doc is the map. When they
  disagree, the code wins and this doc is the bug.
