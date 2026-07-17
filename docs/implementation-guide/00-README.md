# MoneyMatch MVP — Implementation Guide

**Audience:** the implementing agent (Claude Opus) and the team. This guide is the
authoritative plan for taking MoneyMatch from the play-money PoC (the `clutchbook`
repo, mirrored in [`/poc-reference`](../../poc-reference/)) to a launchable MVP
built in *this* repo.

**Read order for a fresh session:**

1. This file — scope, stack decisions, engineering standards.
2. [`01-architecture.md`](./01-architecture.md) — system design, data model, API surface.
3. [`02-design-system.md`](./02-design-system.md) — the visual spec (derived from
   [`docs/design/moneymatch-design.pdf`](../design/moneymatch-design.pdf)).
4. The phase doc you are working on (`03`–`10`).
5. [`11-migration-map.md`](./11-migration-map.md) — exactly what to reuse from the PoC and how.
6. [`12-mvp-acceptance.md`](./12-mvp-acceptance.md) — the definition of done for the MVP.

Product/legal context (read once): [`docs/product/overview.md`](../product/overview.md),
[`docs/legal/legal-compliance.md`](../legal/legal-compliance.md),
[`docs/legal/integrity-audit.md`](../legal/integrity-audit.md).
PoC ground truth: [`poc-reference/POC-IMPLEMENTATION.md`](../../poc-reference/POC-IMPLEMENTATION.md).

Design inputs absorbed into this guide (read when working on matchmaking,
pools, tournaments, or risk):
[`docs/proposals/production-launch-plan-v3.md`](../proposals/production-launch-plan-v3.md)
(duel-forecast pairing, personal-bar pool rooms, matchmade tournaments,
failure-mode matrix, ledger chart of accounts — its Firebase/Stripe stack was
**not** adopted) and
[`docs/proposals/challenge-engine-workflow.md`](../proposals/challenge-engine-workflow.md)
(player performance profiles, challenge immutability/audit, fraud signals,
risk monitoring — its house-backed mode was **rejected**; see the banner on
that doc).

---

## 1. What the MVP is

MoneyMatch is a **peer-to-peer skill-wagering platform on games people already
play**: players stake equal entries into an escrowed pot, play a real match on a
connected game (Chess/Lichess, CS2/FaceIt, Dota 2/OpenDota), results are
**verified against the host game's API**, and the winner takes the pot minus a
fixed, disclosed **rake** — the only revenue. Never house-banked, never
odds-priced. Invariant on every settlement: `sum(payouts) + rake == sum(entries)`.

The MVP is the **no-money product** (roadmap "Stage A", extended): everything a
real launch needs except live payment rails, using **demo money** that flows
through the same real ledger.

### MVP definition (all must hold — details in `12-mvp-acceptance.md`)

- User account creation works (email + Google sign-in).
- FACEIT / Lichess / OpenDota data extraction works; accounts link and profiles render.
- Core challenge flow works end-to-end: pick a market → stake → match with a real
  second user (or invite a friend) → play → auto-verified settlement.
- Match results are verified server-side against host APIs — **zero self-reporting**.
- Basic settlement logic works and is server-authoritative: a tampered client
  cannot change any amount.
- "Demo" deposits and withdrawals work through the real ledger.
- Solo pools and tournaments work with server-fetched telemetry.
- Basic admin tools exist (users, contests, ledger, flags, kill switches).
- Payments/KYC are **integration-ready but not integrated** (interfaces, feature
  flags, DB columns exist; no processor attached).
- Polished UI matching the design PDF; acceptable for real users.
- Internal team can test the whole experience; seed scripts + runbook exist.

### Explicit non-goals for the MVP

- Real money, KYC verification, GPS geolocation (dropdown attestation only, but
  behind an interface).
- Gems economy, seasons, mobile apps, Electron overlay (the PoC overlay is
  legacy and is **not** migrated).
- Rocket League / Clash Royale / any Riot/Epic/Supercell title (publisher ToS —
  see `docs/legal/legal-compliance.md` §2). Do not add "coming soon" surfaces for them.

---

## 2. Stack decisions (settled — do not relitigate mid-build)

| Layer | Choice | Why |
| --- | --- | --- |
| Monorepo | `pnpm` workspaces + top-level Python project; `apps/web`, `apps/api`, `packages/` | One repo, one CI, atomic cross-stack PRs |
| Frontend | React 18 + TypeScript + Vite, Tailwind CSS (+ CSS custom-property tokens), TanStack Query, React Router | PoC parity → maximum reuse; app is behind auth, no SEO need |
| Backend | Python 3.12+ FastAPI as a **long-running service** (not serverless), SQLAlchemy 2 (async) + Alembic, Pydantic v2, httpx | The PoC's adapters/engines/tests are Python and are the crown jewels |
| Database | Postgres 16 (Neon or Supabase hosted; Docker locally) | Ledger + queue need real transactions |
| Auth | Supabase Auth (email + Google OAuth); FastAPI verifies the JWT (JWKS) and owns *all* other state | Fastest credible auth; matches the sign-in design page; no client-side DB access, ever |
| Background work | Dedicated settlement-worker process polling Postgres with `FOR UPDATE SKIP LOCKED` | No Redis/queue infra needed at MVP scale; replaces the PoC's client-side 15 s poll |
| Type sharing | OpenAPI schema from FastAPI → generated TS client (`openapi-typescript` + fetch wrapper) in `packages/api-client` | Kills the PoC's hand-maintained `schemas.py` ↔ `types/index.ts` lockstep |
| Testing | pytest (+ pytest-asyncio, respx), vitest + React Testing Library, Playwright e2e | Testing pyramid; PoC's pytest suites migrate |
| Lint/format | ruff + mypy; eslint + prettier + `tsc --noEmit`; pre-commit | CI-enforced |
| Observability | structlog JSON logs, Sentry (web+api), PostHog via the existing `telemetry.ts` event names | The GTM doc's metrics plan depends on this |
| Deploy | Railway or Render: `api` + `worker` + Postgres; web on Vercel (or same host) | Long-running worker rules out Vercel-only |

### Repo layout (target)

```
moneymatch/
  apps/
    web/                  # React app (Vite)
    api/                  # FastAPI service
      src/moneymatch_api/
        main.py           # app factory, middleware, routers
        config.py         # pydantic-settings; all env in one place
        db/               # engine, session, Alembic migrations
        models/           # SQLAlchemy models (one file per aggregate)
        schemas/          # Pydantic request/response models
        routers/          # auth, wallet, links, play, pools, tournaments, social, admin
        services/         # wallet_service, matchmaking, settlement, telemetry_fetch
        adapters/         # GameAdapter ABC + chess_lichess, cs2_faceit, dota2_opendota
        workers/          # settlement_worker.py (separate entrypoint)
    worker/               # thin entrypoint importing apps/api settlement worker
  packages/
    api-client/           # generated TS client from OpenAPI
  docs/                   # this documentation tree
  poc-reference/          # frozen PoC code — reference only, never imported
  docker-compose.yml      # postgres (+ api/worker for full-stack local)
  .github/workflows/ci.yml
```

`poc-reference/` is **read-only input**: port code out of it (with tests), never
import from it, and never edit it.

---

## 3. Engineering standards (apply in every phase)

1. **Server owns every number.** No money value, timestamp, telemetry, or result
   is ever accepted from the client. Clients send *intents with ids*
   (`join(match_id)`, `enter(pool_id)`); the server computes everything else.
   This is the PoC's #1 lesson (`docs/legal/integrity-audit.md` §2).
2. **Append-only ledger.** Every wallet mutation is a `ledger_entries` row;
   balances are derived (and cached on `wallets` inside the same transaction).
   No `UPDATE wallets SET balance = X` outside the ledger service. A
   reconciliation job asserts the invariant continuously.
3. **Money is integer cents** (`BIGINT`), never floats. The PoC's float math
   (`_round2`) is a known flaw — fix it during the port. Rake computed with
   banker-safe integer math; document rounding (remainder cents go to the rake).
4. **State machines are explicit.** Match/pool/tournament states live in one
   module with legal-transition maps; transitions happen in one service function
   each, inside a DB transaction, emitting ledger + notification events.
5. **Adapters, not imports.** All host-API access goes through the `GameAdapter`
   interface and `registry.get(game_id)`. Settlement logic sees `NormGame` /
   `TelemetrySample`, never raw host JSON.
6. **Schema parity is generated.** Backend Pydantic → OpenAPI → TS client. Never
   hand-write a duplicate type in `apps/web`.
7. **Migrations are forward-only** Alembic revisions; every schema change ships
   with its migration in the same PR.
8. **Tests gate merges.** CI runs ruff/mypy/eslint/tsc + pytest + vitest on every
   PR; Playwright smoke on main. Money-math and settlement paths require tests
   (port the PoC invariant suites first — they're the spec).
9. **Trunk-based git.** Short-lived branches → PR → squash-merge to `main`.
   Conventional-commit subjects (`feat:`, `fix:`, `chore:` …). No secrets in the
   repo — `.env.example` documents every variable; `config.py` fails fast on
   missing ones.
10. **Feature flags & kill switches** come from a `feature_flags` DB table read
    by the API (per-game enable, queue enable, settlement pause). Admin can flip
    them without a deploy — this is an MVP acceptance item.
11. **Compliance invariants in code review:** no odds/lines set by the platform
    (multipliers on screen are *derived* pot math — see `02-design-system.md` §4);
    rake only on distributed prizes (refunds rake nothing); geo-fence checked
    server-side before escrow; excluded-title list respected.

---

## 4. Phase plan (each phase = a shippable increment)

| Phase | Doc | Delivers | Depends on |
| --- | --- | --- | --- |
| 0 — Foundation | [`03-phase-0-foundation.md`](./03-phase-0-foundation.md) | Monorepo scaffold, CI, Docker, auth, app shell + sign-in, design tokens | — |
| 1 — Wallet & ledger | [`04-phase-1-wallet-ledger.md`](./04-phase-1-wallet-ledger.md) | Ledger core, demo deposits/withdrawals, Wallet screen | 0 |
| 2 — Identity & game linking | [`05-phase-2-identity-linking.md`](./05-phase-2-identity-linking.md) | Adapters ported (Lichess/FaceIt/OpenDota), linked accounts, Profile screen | 0 |
| 3 — Head-to-head flow | [`06-phase-3-h2h-flow.md`](./06-phase-3-h2h-flow.md) | DB-backed queue, match lifecycle, settlement worker, Play + Activity screens | 1, 2 |
| 4 — Pools & tournaments | [`07-phase-4-pools-tournaments.md`](./07-phase-4-pools-tournaments.md) | Pool/tournament engines server-side, server-fetched telemetry, Pools + Tournament screens | 3 |
| 5 — Social & retention | [`08-phase-5-social-retention.md`](./08-phase-5-social-retention.md) | Friends, invites/challenges, Inbox + notifications, Leaderboard | 3 |
| 6 — Admin & instrumentation | [`09-phase-6-admin-ops.md`](./09-phase-6-admin-ops.md) | Admin surface, kill switches, PostHog events, reconciliation dashboard | 1–5 |
| 7 — Hardening & internal beta | [`10-phase-7-hardening-beta.md`](./10-phase-7-hardening-beta.md) | Payments/KYC-ready seams, e2e suite, polish pass, seed data, runbook, beta | all |

Rules of engagement per phase: finish the phase's **exit criteria** (each phase
doc ends with them) before starting the next; anything discovered out-of-scope
goes into `docs/implementation-guide/BACKLOG.md` rather than expanding the phase.
Phases 4 and 5 can proceed in parallel once 3 is done.
