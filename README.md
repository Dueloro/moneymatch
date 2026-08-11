# Money Match

> **Peer-to-peer skill wagering on the games you already play.**
> Stake an equal entry into an escrowed pot, play a real match on a connected
> game, and the winner takes the pot minus a small, disclosed fee. We hold the
> pot. We never take a side.

Money Match is a contest-of-skill platform built **on top of games people already play**
(Chess, CS2, Dota 2, PUBG). Players stake into a shared pot, results are
**auto-verified against the host game's API**, and the
winner takes the pot minus a **fixed, disclosed rake**, which is the platform's only
revenue. Never house-banked, never odds-priced.

This repository is the **MVP build**: everything a real launch needs except live
payment rails, running on **demo money that flows through the same real ledger**.

_Money Match is developed by [Dueloro](https://dueloro.com)._

---

## Why it's built the way it is

The whole system is organized around five invariants. They are what make the
model legally defensible and the ledger auditable.

1. **`sum(payouts) + rake == sum(entries)`** on every settlement path. The
   platform's books never carry outcome risk. Only the rake accrues.
2. **The server owns every number.** No client-supplied amount, timestamp,
   telemetry, or result is ever trusted. Clients send _intents with ids_, the
   server computes the rest.
3. **Settlements are host-API-verified.** No self-reporting, no screenshots.
4. **Rake only when a prize distributes.** Refunds and pushes rake nothing, so the
   platform never profits from a player failing.
5. **Money is integer cents**, in an append-only ledger so balances are derived and
   reconciled continuously.

Read [`docs/decisions.md`](./docs/decisions.md) for the settled architecture and
product decisions and the reasoning behind each.

---

## Start here (documentation map)

For onboarding a developer, briefing a reviewer, or pointing an AI agent at the
codebase:

| Doc                                                                                                            | What it gives you                                                                    |
| -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| [`docs/implementation-guide/implementation-summary.md`](./docs/implementation-guide/implementation-summary.md) | **The as-built system** — architecture, stack, per-area feature inventory, standards |
| [`docs/decisions.md`](./docs/decisions.md)                                                                     | The "do not relitigate" architecture & product decisions + why                       |
| [`docs/data-model.md`](./docs/data-model.md)                                                                   | Map of the database: tables, the ledger, the invariants                              |
| [`docs/design-guidelines.md`](./docs/design-guidelines.md)                                                     | The UI design system: tokens, type, components, patterns, copy                       |
| [`docs/adding-a-game.md`](./docs/adding-a-game.md)                                                             | How a new title plugs in via the `GameAdapter` seam                                  |
| [`docs/product/overview.md`](./docs/product/overview.md)                                                       | The full product definition and the peer-to-peer / rake-only rationale               |
| [`docs/legal/`](./docs/legal/) · [`docs/business/`](./docs/business/)                                          | Compliance posture, integrity threat model, economics, GTM                           |
| [`docs/implementation-guide/BACKLOG.md`](./docs/implementation-guide/BACKLOG.md)                               | What's pending / not yet built                                                       |
| [`docs/`](./docs/README.md)                                                                                    | Full index of every doc                                                              |

---

## Architecture at a glance

A React SPA talks **only** to a FastAPI service that owns all state. A dedicated
worker settles contests in the background against host-game APIs.

```
Browser (React SPA) ──HTTPS──▶ FastAPI service ──▶ Postgres (ledger + queue)
   auth via Supabase JWT          owns every number        ▲
                                        │                  │
                              Settlement worker ──polls──▶ host game APIs
                              (grades + settles)           (Lichess / FACEIT / …)
```

| Layer         | Choice                                                                                                               |
| ------------- | -------------------------------------------------------------------------------------------------------------------- |
| Frontend      | React 18 + TypeScript + Vite, Tailwind (CSS-var tokens), TanStack Query                                              |
| Backend       | Python 3.12 FastAPI (long-running), async SQLAlchemy 2 + Alembic, Pydantic v2                                        |
| Database      | Postgres 16 (append-only ledger + `FOR UPDATE SKIP LOCKED` queue)                                                    |
| Auth          | Supabase Auth (email + Google); the API verifies the JWT and owns all other state — the browser never touches the DB |
| Background    | Dedicated settlement worker; host-API-verified grading                                                               |
| Types         | Pydantic → OpenAPI → generated TS client (`packages/api-client`)                                                     |
| Observability | structlog JSON logs, Sentry, PostHog                                                                                 |
| Deploy        | Render (`api` + `worker` + Postgres/Neon); web on Vercel                                                             |

### Repo layout

```
apps/web            React + Vite SPA (talks only to the API)
apps/api            FastAPI service (owns every number; verifies Supabase JWTs)
apps/worker         Settlement worker entrypoint
packages/api-client Generated TypeScript client (OpenAPI → TS)
docs/               Implementation summary, decisions, design guidelines,
                    data model, product, legal, business
```

---

## Quickstart (local development)

Prerequisites: **Docker**, **Node 20+** with `pnpm` (via `corepack enable pnpm`),
and [**uv**](https://docs.astral.sh/uv/) for the Python API.

```bash
cp .env.example .env   # fill in the Supabase keys — see the note below
make install           # pnpm workspace + API venv
make dev               # Postgres + API + web together
```

Open http://localhost:5173, sign in, complete onboarding
(username, state, age), and land on the Play screen.

Individual pieces (each reads the root `.env`):

| Command                        | What it does                                      |
| ------------------------------ | ------------------------------------------------- |
| `make db`                      | Start Postgres (Docker) and wait until healthy    |
| `make migrate`                 | Apply Alembic migrations                          |
| `make api`                     | Run the FastAPI service on :8000 (reload)         |
| `make web`                     | Run the Vite dev server on :5173                  |
| `make test`                    | Run API (pytest) + web (vitest) suites            |
| `make lint` / `make typecheck` | ruff/prettier + mypy/tsc                          |
| `make gen-api`                 | Regenerate the TS API client from the running API |
| `make help`                    | List all commands                                 |

**Port note:** if `5432` is taken, set `DB_PORT` in `.env` and update the port in
`DATABASE_URL` to match.

---

## Admin & operations

The operator surface lives at **`/admin`**. It lets us search users and inspect any money trail, freeze users,
make audited ledger adjustments, re-settle or void a stuck match, flip kill
switches (`queue_paused`, `settlement_paused`, per-game enable, `geo_config`)
without a deploy, run reconciliation on demand, and work the risk / sandbagging
flag queue. Every admin mutation writes an `admin_audit` row.

| Task                        | Command                                                            |
| --------------------------- | ------------------------------------------------------------------ |
| Grant admin (audited)       | `cd apps/api && uv run python ../../scripts/grant_admin.py <user>` |
| Seed a demoable environment | `cd apps/api && uv run python ../../scripts/seed_demo.py`          |

`GET /api/v1/health` reports the settlement worker's health (`worker.stale`
reddens if the worker hasn't cycled in > 2 min). The same signal shows on the
admin **Reconciliation** tab.
