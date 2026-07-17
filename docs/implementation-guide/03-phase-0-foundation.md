# Phase 0 — Foundation & Scaffolding

**Objective:** a running skeleton — monorepo, CI, local Postgres, auth, the app
shell with sidebar + sign-in flow — so every later phase only adds features.

**Depends on:** nothing. **Unblocks:** everything.

---

## Deliverables

1. Monorepo per the layout in `00-README.md` §2 (`apps/web`, `apps/api`,
   `packages/api-client`), pnpm workspaces + `pyproject.toml` (uv or pip-tools)
   for the API.
2. `docker-compose.yml`: Postgres 16 (+ optional api/worker services). `make dev`
   (or `justfile`) starts db + api + web with one command.
3. FastAPI app factory with: `config.py` (pydantic-settings, fail-fast),
   structlog JSON logging, Sentry init, CORS for the web origin, `/api/v1/health`,
   Alembic wired with an initial empty migration.
4. Supabase project + Auth: email/password and Google. Backend JWT verification
   middleware (JWKS cache) → `request.state.user` resolves/creates the `users`
   row on first authed call.
5. First real migration: `users`, `feature_flags`, `admin_audit` tables
   (see `01-architecture.md` §2).
6. Web app: Vite + Tailwind mapped to the design tokens (`02-design-system.md`
   §1), React Router, TanStack Query, Supabase JS auth session, generated API
   client wired (`pnpm gen:api` pulls OpenAPI from the running api).
7. Screens: **Sign-in** (PDF p.13: Google + email, 3-step progress —
   auth → username + US-state + 18+ attestation → "link your first game" stub)
   and the **app shell** (sidebar nav, footer breadcrumb, empty routed pages for
   Play/Pools/Tournament/Activity/Wallet/Inbox/Profile).
8. CI (GitHub Actions): jobs for `ruff+mypy+pytest` and
   `eslint+prettier-check+tsc+vitest+build`, on every PR; branch protection notes
   in `CONTRIBUTING.md`.
9. Repo hygiene: `.env.example` (every var documented), `README.md` with real
   run instructions, `CONTRIBUTING.md` (branch/commit/test conventions from
   `00-README.md` §3), `.gitignore`, pre-commit config.

## Key tasks & notes

- **Config keys (initial):** `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET`
  (or JWKS URL), `SENTRY_DSN` (optional), `FACEIT_API_KEY` (used from Phase 2),
  `WEB_ORIGIN`, `ENV`.
- **Username rules:** 3–20 chars `[a-z0-9_]`, unique citext; chosen at
  onboarding step 2, changeable never (MVP) — it's the public handle in queues.
- **Residence + 18+ gate:** stored on `users`; the excluded-state list goes in a
  `geo_config` feature-flag payload (NOT a code constant). Seed with the 14
  states from the PoC (`poc-reference/frontend/src/utils/states.ts`). Blocked
  states can still sign in (free-play-everywhere posture) — enforcement happens
  at escrow time per `01-architecture.md` §3.2.
- **Feature flags:** seed `game:chess.lichess`, `game:cs2.faceit`,
  `game:dota2.opendota` (enabled), `queue_paused=false`, `settlement_paused=false`.
- Do **not** build wallet UI, adapters, or any game logic in this phase.

## Reuse from `poc-reference/`

| What | From | Note |
| --- | --- | --- |
| Excluded-states list | `frontend/src/utils/states.ts` | becomes `geo_config` seed data |
| Telemetry event names | `frontend/src/utils/telemetry.ts` | keep names; sink comes in Phase 6 |
| Design tokens approach | `frontend/src/index.css` | structure only — values change to `02-design-system.md` |

## Tests required

- API: health endpoint; JWT middleware (valid/expired/garbage token); user
  auto-provisioning on first call; config fail-fast on missing env.
- Web: sign-in flow renders; route guard redirects unauthed → sign-in; vitest
  smoke on the shell.

## Exit criteria

- [ ] `make dev` → sign in with Google or email → complete onboarding →
      land on empty Play screen with sidebar, in <10 min from fresh clone.
- [ ] `users` row created with username/state/attestation; second login reuses it.
- [ ] CI green on a PR touching both `apps/web` and `apps/api`.
- [ ] No secrets in repo; `.env.example` complete.
