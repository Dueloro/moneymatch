# MoneyMatch MVP — Implementation Summary (as built)

**What this is.** A single reference for what the MVP *is today*, replacing the
phased build plan (phases 0–7, architecture, design-system, migration-map,
acceptance, hosting, UI revamp/current-state docs) now that the work they
described is built. For **pending / not-yet-built** work, see
[`BACKLOG.md`](./BACKLOG.md). For the UI, see
[`../design-guidelines.md`](../design-guidelines.md). For operations, see
[`../runbook.md`](../runbook.md).

**Status:** Phases 0–7 are code-complete. What remains are human/infra steps that
cannot be self-completed — stand up staging + production, run the ≥1-week internal
beta, capture the PostHog metrics snapshot, do a rollback drill, and have a
non-author sign off the acceptance checklist. See [`BACKLOG.md`](./BACKLOG.md)
("Discovered during Phase 7").

---

## 1. The product

A **peer-to-peer skill-wagering platform** on games people already play. Players
stake equal entries into an escrowed pot, play a real match on a connected game
(Chess/Lichess, CS2/FACEIT, Dota 2/OpenDota, PUBG), results are **verified
against the host game's API**, and the winner takes the pot minus a fixed,
disclosed **rake** — the only revenue. Never house-banked, never odds-priced.

The MVP is the **no-money product**: everything a real launch needs except live
payment rails, using **demo money** that flows through the same real ledger.

### Invariants (never violated)

1. `sum(payouts) + rake == sum(entries)` on every settlement path.
2. The server owns every number — no client-supplied amounts, timestamps,
   telemetry, or results.
3. Settlements are host-API-verified. No self-reporting, no screenshots.
4. Rake only when a prize distributes; refunds and pushes rake nothing.
5. Money is integer cents (`BIGINT`). Rake is config (basis points), never an
   odds line; default 1000 bps = 10%.

---

## 2. Stack

| Layer | Choice |
| --- | --- |
| Monorepo | `pnpm` workspaces + top-level Python; `apps/web`, `apps/api`, `apps/worker`, `packages/api-client` |
| Frontend | React 18 + TypeScript + Vite, Tailwind (+ CSS custom-property tokens), TanStack Query, React Router |
| Backend | Python 3.12+ FastAPI as a **long-running service**, SQLAlchemy 2 (async) + Alembic, Pydantic v2, httpx |
| Database | Postgres 16 (Neon/Supabase hosted; Docker locally) |
| Auth | Supabase Auth (email + Google OAuth); FastAPI verifies the JWT (JWKS) and owns all other state. The browser never touches the DB |
| Background work | A dedicated settlement-worker process polling Postgres with `FOR UPDATE SKIP LOCKED` |
| Type sharing | OpenAPI schema from FastAPI → generated TS client in `packages/api-client` |
| Testing | pytest (+ pytest-asyncio, respx), vitest + React Testing Library, Playwright e2e |
| Observability | structlog JSON logs, Sentry (web+api), PostHog analytics |
| Deploy | Render (`api` + `worker` + Postgres) / Neon; web on Vercel |

### Repo layout

```
apps/
  web/                    React SPA (talks only to the API)
  api/src/moneymatch_api/
    main.py               app factory, middleware, routers
    config.py             pydantic-settings; all env in one place
    db/                   engine, session, Alembic migrations
    models/               SQLAlchemy models (one file per aggregate)
    schemas/              Pydantic request/response models
    routers/              auth, wallet, links, play, pools, tournaments,
                          social, admin, disputes, chat, …
    services/             wallet, matchmaking, settlement, telemetry_fetch, …
    adapters/             GameAdapter ABC + chess_lichess, cs2_faceit,
                          dota2_opendota, pubg
    payments/  kyc/       integration-ready seams (no live processor)
    workers/              settlement worker (separate entrypoint)
  worker/                 thin entrypoint importing the settlement worker
packages/api-client/      generated TS client from OpenAPI
docs/                     this documentation tree
```

---

## 3. Engineering standards (in force)

1. **Server owns every number.** Clients send intents with ids
   (`join(match_id)`, `enter(pool_id)`); the server computes everything else.
2. **Append-only ledger.** Every wallet mutation is a `ledger_entries` row;
   balances are derived (and cached on `wallets` in the same transaction). No
   `UPDATE wallets SET balance` outside the ledger service. A reconciliation job
   asserts the invariant continuously.
3. **Money is integer cents**, never floats. Rake uses floor integer math
   (remainder cents accrue to the rake).
4. **State machines are explicit** — match/pool/tournament states in one module
   with legal-transition maps; each transition is one service function inside a
   DB transaction, emitting ledger + notification events.
5. **Adapters, not imports.** All host-API access goes through `GameAdapter` +
   `registry.get(game_id)`. Settlement sees normalized `NormGame` /
   `TelemetrySample`, never raw host JSON.
6. **Schema parity is generated** (Pydantic → OpenAPI → TS client). Never
   hand-write a duplicate type in `apps/web`.
7. **Migrations are forward-only** Alembic revisions, shipped in the same PR as
   the schema change.
8. **Tests gate merges** (ruff/mypy/eslint/tsc + pytest + vitest in CI). Money-
   math and settlement paths require tests.
9. **Trunk-based git**, short-lived branches, conventional-commit subjects, no
   secrets in the repo (`.env.example` documents every variable; `config.py`
   fails fast on missing ones).
10. **Feature flags & kill switches** live in a DB table read by the API
    (per-game enable, queue enable, settlement pause), flippable without a deploy.
11. **Compliance invariants in review:** no platform-set odds/lines (multipliers
    are derived pot math); rake only on distributed prizes; geo-fence checked
    server-side before escrow; excluded-title list respected.

---

## 4. What is built, by area

### Foundation & auth
Monorepo scaffold, CI (ruff/mypy/eslint/tsc + pytest + vitest, Playwright smoke),
Docker, Supabase auth (email + Google), app shell + sign-in, design tokens.

### Wallet & ledger
Append-only `ledger_entries`; derived, transaction-cached balances (available /
in-play / locked); demo deposits/withdrawals through the real ledger; the Wallet
screen. Reconciliation asserts the invariant on demand and can pause settlement.

### Identity & game linking
Four adapters ported and live via username-claim: **Chess/Lichess**,
**CS2/FACEIT**, **Dota 2/OpenDota**, **PUBG**. Linked accounts, profile snapshots,
skill-metric bootstrapping from real match history, per-metric models
(`metric_models`), and immutable-ish bindings with **soft-unbind** (`status =
'unbound'`, history retained) so a played account can be rebound. Raw host
payloads retained for audit (`raw_payloads`).

### Head-to-head flow
DB-backed matchmaking queue (`FOR UPDATE SKIP LOCKED`), duel-forecast pairing,
the full match lifecycle state machine, and the **settlement worker** that polls
host APIs, grades server-side, and settles with the money invariant asserted
(winner +$18 / loser −$10 / rake $2 on a $10 H2H). Brokered Lichess challenges
for chess. Play + Activity screens.

### Pools & tournaments
Server-side pool engine (personal-bar rooms with averaged room bars, fair-room
composition) and tournament engine (matchmade stat tournaments, top-3 split),
both with **server-fetched telemetry** (zero self-reporting). Pools + Tournament
screens with the clear bar and live standings.

### Social & retention
Friends + friend codes, invites/challenges (single-use tokens, public preview,
fresh-signup accept), the two-pane **Inbox** (friend DMs, a MoneyMatch Support
thread, in-thread invite cards — see the chat services/components), notifications,
and the Leaderboard (ROI). Challenge deep-links route to the Play confirm card.

### Admin & instrumentation
The `/admin` operator surface (dense, plain, outside the design system): user
search + money-trail inspection, freezes, audited ledger adjustments, re-settle /
void stuck **matches**, kill switches (`queue_paused`, `settlement_paused`,
per-game enable, `geo_config`) without a deploy, on-demand reconciliation, and a
risk/sandbagging flag queue. Every admin mutation writes an `admin_audit` row.
**PostHog** money/liquidity events server-side and the activation funnel
client-side. Health endpoint reports the settlement worker's heartbeat
(`worker.stale`).

### Risk & integrity
Sandbagging detection (folds off the hot path into a nightly sweep + cheap
`risk_flags` check on rake-bearing enqueue), a `win_streak` derived detector,
pair-frequency awareness, and a **disputes** model + operator-mediated review
(self-report is deliberately absent).

### Payments / KYC readiness
`payments/` (`PaymentProvider` protocol + `DemoProvider`) and `kyc/`
(`KycProvider` protocol + `users.kyc_status` + a `kyc_required` policy hook that
returns `False` at MVP but is *called* at every deposit/withdrawal/threshold
site). Phase-1 caps are config-driven. Flags `payments_live` / `kyc_live` are
**code-guarded** — flipping config alone is inert. No live processor is attached.

### Hardening
AuthZ/IDOR test matrix, in-process rate limiting on auth-sensitive/write
endpoints, input size caps, web security headers/CSP, dependency audits in CI,
and chaos-style tests (worker killed mid-settlement is re-claimable and never
double-pays; host outage cancels + refunds at window end). A `demo/relink` seam
lets the shared demo user swap in a real host handle to exercise the live linking
pipeline (`docs/game/testing-chess.md`).

---

## 5. Non-goals for the MVP (by design, not gaps)

- Real money, KYC verification, GPS geolocation (dropdown attestation only,
  behind an interface).
- Gems economy, seasons, mobile apps, the Electron overlay.
- Rocket League / Clash Royale / any Riot/Epic/Supercell title (publisher ToS —
  see [`../legal/legal-compliance.md`](../legal/legal-compliance.md) §2). No
  "coming soon" surfaces for them.
- OAuth account binding (Lichess/FACEIT/Steam) — username-claim is the live path;
  OAuth needs registered apps and is the first pre-beta integrity item in
  [`BACKLOG.md`](./BACKLOG.md).

---

## 6. Where to go next

- **Pending / discovered work:** [`BACKLOG.md`](./BACKLOG.md).
- **UI system:** [`../design-guidelines.md`](../design-guidelines.md).
- **Operations:** [`../runbook.md`](../runbook.md).
- **Product / legal / business context:** [`../product/overview.md`](../product/overview.md),
  [`../product/roadmap.md`](../product/roadmap.md),
  [`../legal/legal-compliance.md`](../legal/legal-compliance.md),
  [`../legal/integrity-audit.md`](../legal/integrity-audit.md).
- **Host API references & local testing:** [`../game/`](../game/).
