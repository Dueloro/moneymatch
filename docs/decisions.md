# Architecture & Product Decision Log

The settled, "do not relitigate mid-build" decisions and *why* they were made, so
a new contributor (or agent) doesn't reopen a closed question. Each entry is a
decision, its context, and its consequence. If you want to change one, that is a
real proposal with a reason — not a drive-by refactor.

Format: **Decision** · why · what it costs/enables. Newest concerns first within
each group.

---

## Product & legal frame (load-bearing — these define the company)

- **Peer-to-peer / pooled, rake-only, never house-banked.** The platform takes a
  fixed disclosed fee off the pot and holds **zero** outcome position. This is the
  legal core (contest-of-skill + neutral-operator, the Skillz/Triumph frame), not
  a cosmetic choice. *Consequence:* no feature may put the house on the other side
  of a wager — including the rejected "clear a bar, win a platform-funded fixed
  prize" solo mode. Solo challenges ship **pooled** (entrant-funded, rake-only).
  See [`product/overview.md`](./product/overview.md) §2, §10.4.
- **Rake is a disclosed service fee, never an odds line.** Configured in basis
  points per game/format (`services/money_math.py`, default 1000 bps = 10%). The
  same fee applies whoever wins; on-screen "multipliers" are *derived pot math*,
  not platform-set odds. *Consequence:* a fee that varied with the outcome would
  re-create a vig and break the legal frame.
- **Rake only when a prize distributes.** Refunds and pushes rake nothing; a solo
  pool with no clearers refunds fully. *Why:* the platform must never profit from
  a player failing.
- **Chess (Lichess) is the hero game; Riot/Epic/Supercell titles are excluded.**
  Publisher ToS forbids the money layer for those (Rocket League, Clash Royale,
  Valorant, …). *Consequence:* no "coming soon" surfaces for excluded titles. See
  [`legal/legal-compliance.md`](./legal/legal-compliance.md) §2.
- **MVP is demo-money through the real ledger, not a mock.** Demo deposits/
  payouts are real `ledger_entries` rows funded from `platform:promo`. *Why:* the
  money machinery is exercised for real before cash rails attach; nothing about
  the ledger changes when `payments_live` flips.

## Server-authoritative architecture

- **The server owns every number.** Clients send *intents with ids*
  (`join(match_id)`, `enter(pool_id)`); the server computes every amount,
  timestamp, telemetry value, and result. *Why:* the PoC's #1 integrity flaw was
  client-owned state ([`legal/integrity-audit.md`](./legal/integrity-audit.md)
  §1–3). *Consequence:* no client-supplied money value is ever accepted, and no
  duplicate money type lives in the web app.
- **Append-only ledger; balances are derived.** Every wallet mutation is a
  `ledger_entries` row; `wallets` caches balances inside the same transaction. No
  `UPDATE wallets SET balance` outside the ledger service. A reconciliation job
  asserts `sum(payouts) + rake == sum(entries)` continuously. *Why:* this is the
  audit substrate for Stage-C AML/SAR duties — build it right once.
- **Money is integer cents (`BIGINT`), never floats.** Rake uses floor integer
  math; remainder cents accrue to the rake. *Why:* the PoC's float `_round2` was a
  known defect.
- **Settlement is host-API-verified.** No self-reporting, no screenshots. Solo/
  tournament telemetry is fetched server-to-server; the "I cleared it" buttons are
  gone. *Consequence:* a game with no server-fetchable telemetry does not get solo
  pools.
- **State machines are explicit.** Match/pool/tournament states live in one module
  with legal-transition maps; each transition is one service function inside a DB
  transaction that emits ledger + notification events.

## Stack

- **Long-running FastAPI + a dedicated settlement worker + Postgres — not
  Firebase/Firestore, not serverless, not Vercel-cron.** The v3 launch plan's
  Firebase/Stripe stack was **not adopted**; same server-authoritative principles,
  different substrate. *Why:* the ledger + matchmaking queue need real
  transactions, and a background settlement worker (polling with `FOR UPDATE SKIP
  LOCKED`) rules out a Vercel-only deploy. No Redis at MVP scale.
- **Supabase Auth (email + Google); the API verifies the JWT and owns all other
  state.** The browser never touches the database. *Why:* fastest credible auth;
  keeps a single source of truth in the API.
- **Adapters, not imports.** All host-API access goes through the `GameAdapter`
  interface + `registry.get(game_id)`; settlement sees normalized `NormGame` /
  `TelemetrySample`, never raw host JSON. *Why:* adding a title must not touch
  matchmaking/escrow/settlement. See [`adding-a-game.md`](./adding-a-game.md).
- **Types are generated, not hand-synced.** Pydantic → OpenAPI → TS client in
  `packages/api-client`. *Why:* kills the PoC's hand-maintained schema↔types
  lockstep.

## Identity, risk, payments

- **Username-claim is the MVP linking path; OAuth is deferred.** Lichess/FACEIT/
  Steam OAuth needs registered apps and is the first pre-beta integrity item.
  *Consequence:* bindings currently key on the (mutable) host handle; binding by
  immutable host id lands with OAuth. See [`BACKLOG.md`](./implementation-guide/BACKLOG.md).
- **Bindings soft-unbind, never hard-delete.** `status='unbound'` retains the row
  for FK history so a played account can be rebound. *Why:* `match_players` FKs are
  `RESTRICT`; a hard delete would fail and strand history.
- **Payments/KYC ship as code-guarded seams, not config flags.** `payments_live` /
  `kyc_live` require a code + config change to enable; flipping config alone is
  inert. *Why:* real rails are gated on counsel + underwriting and must not be
  switch-on-able by accident.
- **Self-report is deliberately absent; disputes are operator-mediated.** *Why:*
  results are host-verified by construction, so a "flag this result" path routes
  to a human, never overrides the ledger.

## UI & process

- **Admin is intentionally outside the consumer design system.** Dense monospace
  internal tool. *Why:* it should look like one; the consumer shell stays clean.
- **No seeded/bot liveness in the UI.** The ticker/queue render only from real
  players and hide when empty. *Why:* a wagering audience distrusts fabricated
  counts. (The one violation, `filledSpots()`, is flagged for a product decision —
  [`design-guidelines.md`](./design-guidelines.md) §10.)
- **Trunk-based git, forward-only migrations, tests gate merges.** Every schema
  change ships its Alembic revision in the same PR; money-math and settlement
  paths require tests.
