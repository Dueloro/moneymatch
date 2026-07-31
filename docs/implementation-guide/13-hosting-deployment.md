# Hosting & Deployment Guide

Complete walkthrough for deploying MoneyMatch from scratch: Supabase (auth) →
Render (API + worker + Postgres) → Vercel (web). Read top-to-bottom in order
the first time; the dependency chain is: **Supabase must exist before Render can
boot, Render must be up before Vercel is wired.**

Estimated wall-clock time on a first deploy: ~45 minutes.

---

## 1. What runs where

| Component | Platform | Notes |
| --- | --- | --- |
| Postgres 16 | Render Managed Postgres | Ledger, queue, all server state |
| `api` (FastAPI/uvicorn) | Render Web Service | Stateless; scale horizontally later |
| `settlement-worker` | Render Background Worker | Single write path for settlements |
| `web` (React/Vite SPA) | Vercel | Static build; no server-side rendering |
| Auth | Supabase | JWTs verified by the API; no DB access from the browser |

The `render.yaml` blueprint at the repo root declares the Postgres instance plus
both services. Vercel is configured by `apps/web/vercel.json`.

---

## 2. Prerequisites

Before touching any dashboard, have these ready:

- **GitHub repo access** — Render and Vercel both connect via GitHub. The
  deploying account needs read access to `Dueloro/moneymatch` (or your fork).
- **FaceIt server-side API key** — get one at
  `developers.faceit.com` → Applications → Server side key. This is required
  for CS2 match telemetry; without it the CS2 adapter returns errors but the
  app still boots.
- **Sentry project** (optional but strongly recommended) — create two projects
  (one `python`, one `react`) at `sentry.io`. You get two DSNs.
- **PostHog project** (optional) — create a project at `posthog.com`; you get
  a server-side API key and a browser-side project key (different values, same project).

---

## 3. Supabase setup

Supabase handles all user authentication. The API verifies the JWTs it issues;
the browser uses the anon key to start auth sessions. **The API never touches
Supabase's database** — all game/wallet/ledger data lives in the Render Postgres.

### 3.1 Create a project

1. Go to `supabase.com` → New project. Choose a strong DB password (you won't
   need it directly, but save it).
2. Pick the region closest to your Render services (both in `us-east-1` or
   both in `eu-west-2`, for example).
3. Wait for provisioning (~2 min).

### 3.2 Collect credentials

From the Supabase dashboard → **Settings → API**:

| Value | Where to find it | Used by |
| --- | --- | --- |
| **Project URL** | "Project URL" box, e.g. `https://abcxyz.supabase.co` | API (`SUPABASE_URL`) and web (`VITE_SUPABASE_URL`) |
| **anon / public key** | "Project API keys" → `anon public` | Web only (`VITE_SUPABASE_ANON_KEY`) |
| **JWT Secret** | Settings → API → "JWT Settings" → "JWT Secret" | API only (`SUPABASE_JWT_SECRET`) — never expose to the browser |

### 3.3 Enable auth providers

Go to **Authentication → Providers**:

- **Email** — enabled by default. Set "Confirm email" to on (recommended) or
  off for an internal beta where you trust everyone.
- **Google** (optional for MVP) — requires a Google Cloud OAuth client
  (`console.cloud.google.com` → APIs & Services → Credentials → OAuth 2.0 client).
  Paste Client ID + Secret into Supabase. The redirect URL to whitelist is
  `https://<your-supabase-project>.supabase.co/auth/v1/callback`.

### 3.4 Add redirect URLs

Go to **Authentication → URL Configuration**:

- **Site URL** — set to your Vercel URL: `https://moneymatch-beta.vercel.app`
  (or your custom domain).
- **Additional redirect URLs** — add the same Vercel URL, plus
  `http://localhost:5173` for local development.

If these aren't set, Supabase will reject OAuth callbacks and email confirmation
links will not land correctly.

---

## 4. Render setup

Render hosts the long-running API, the settlement worker, and the Postgres
database. All three are declared in `render.yaml` at the repo root, which you
can use as a blueprint import, or create each service manually.

### 4.1 Option A — Blueprint import (recommended)

1. Render dashboard → **Blueprints → New Blueprint Instance**.
2. Connect the `Dueloro/moneymatch` GitHub repo.
3. Render detects `render.yaml` and shows the three resources: `moneymatch-postgres`,
   `moneymatch-api`, `moneymatch-worker`.
4. Click **Apply**. Render creates all three. The API and worker will fail to
   start until env vars are set in step 4.3 — that is expected.

### 4.2 Option B — Manual creation

Skip this if you used the blueprint.

**Create Postgres first:**

- New → PostgreSQL → name it `moneymatch-postgres`.
- Plan: **Standard** (required for PITR; the free plan has no backups).
- Postgres version: **16**.
- Save the **Internal Database URL** shown after creation.

**Create the API web service:**

- New → Web Service → connect the repo.
- Runtime: **Docker**.
- Dockerfile path: `apps/api/Dockerfile`.
- Docker build context: `.` (repo root — not `apps/api`; the Dockerfile copies
  from `apps/api/` relative to the repo root).
- Health check path: `/api/v1/health`.
- Pre-deploy command: `alembic upgrade head`
  (runs once per deploy before traffic switches; `alembic` is on PATH from the
  system-wide install in the image).
- Start command (override the Dockerfile default): `uvicorn moneymatch_api.main:app --host 0.0.0.0 --port $PORT`
  (Render assigns a dynamic `$PORT`; the Dockerfile hardcodes 8000 which breaks
  the health check).
- Plan: **Starter** or higher.

**Create the worker service:**

- New → Background Worker → same repo.
- Runtime: **Docker**.
- Same Dockerfile path (`apps/api/Dockerfile`) and build context (`.`).
- Start command: `python -m moneymatch_api.workers.settlement_worker`
- No health check, no port needed.
- Plan: Starter.

### 4.3 Set environment variables

Set these on **both** the API web service and the worker (they share `config.py`
and the worker still validates all settings at startup):

**Required — the service won't boot without these:**

| Key | Value | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Internal Database URL from Render Postgres | Must start with `postgresql+asyncpg://` — Render gives `postgres://` or `postgresql://`, rewrite the scheme. Example: `postgresql+asyncpg://user:pass@host/db` |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | From Supabase → Settings → API |
| `SUPABASE_JWT_SECRET` | the JWT secret | From Supabase → Settings → API → JWT Settings — **never** put this in Vercel |
| `WEB_ORIGIN` | `https://moneymatch-beta.vercel.app` | Your Vercel URL; CORS allow-list. Comma-separate if you add a custom domain: `https://moneymatch.gg,https://moneymatch-beta.vercel.app` |
| `ENV` | `prod` | Controls structured JSON logging and disables debug middleware |

**Required for the product to work:**

| Key | Value | Notes |
| --- | --- | --- |
| `FACEIT_API_KEY` | your FaceIt server API key | CS2 settlement fails without it; Chess and Dota 2 still work |

**Strongly recommended:**

| Key | Value | Notes |
| --- | --- | --- |
| `SENTRY_DSN` | Python project DSN | Error tracking for the API and worker |
| `RELEASE` | git SHA of the deploy | Tags Sentry events; set it from your deploy pipeline or enter it manually after each deploy |
| `POSTHOG_API_KEY` | server-side PostHog key | Server-side event capture; empty = silently no-ops |
| `POSTHOG_HOST` | `https://us.i.posthog.com` | Default; override only if you use EU PostHog |

**Optional (defaults are safe for MVP):**

| Key | Default | Change if... |
| --- | --- | --- |
| `PAYMENTS_LIVE` | `false` | Leave false. Flipping to true without a live PaymentProvider compiled in raises `PaymentsMisconfiguredError` at startup — it is code-guarded, not just config-guarded. |
| `KYC_LIVE` | `false` | Same guard. Leave false for beta. |
| `MAX_REQUEST_BYTES` | `65536` (64 KB) | Only raise if you add file-upload endpoints. |
| `RATE_LIMIT_WRITES_PER_MINUTE` | `60` | Per-IP per-minute cap on write endpoints. Lower for abuse protection; raise if load tests show false positives. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | Only change if your Supabase project uses a custom audience. |
| `SLOW_HOST_MS` | `2000` | Logs a warning when a host-API call (FaceIt, Lichess, OpenDota) exceeds this. |

### 4.4 DATABASE_URL scheme conversion

Render's Postgres "Internal Database URL" looks like:

```
postgresql://moneymatch_user:password@dpg-xxx.render.com/moneymatch_db
```

The async SQLAlchemy driver needs `postgresql+asyncpg://`. Copy the URL and
replace only the scheme prefix:

```
postgresql+asyncpg://moneymatch_user:password@dpg-xxx.render.com/moneymatch_db
```

Use the **Internal** URL (not External) when the API and Postgres are on the
same Render account — internal connections skip the public internet and are faster.

### 4.5 Verify the API is up

After setting env vars, trigger a manual deploy (Render dashboard → the web
service → Deploy). Watch the deploy log:

1. Pre-deploy command runs: you should see Alembic output like
   `Running upgrade -> 0001_initial, ...` and finally `Done.`.
2. Service starts: uvicorn logs `Application startup complete`.
3. Health check passes: Render shows the service as **Live**.

Test it:

```
curl https://<your-render-api-url>/api/v1/health
```

Expected response (abbreviated):
```json
{"status": "ok", "worker_alive": false, "games": {...}}
```

`worker_alive: false` is expected until the worker has run its first cycle
(within ~15 seconds of the worker service starting).

### 4.6 Verify the worker is up

The worker writes a heartbeat to `feature_flags.worker_heartbeat` each cycle.
The API's `/health` endpoint reads it and reddens when it is stale (> 120 s).
Give the worker service ~30 seconds to start, then re-check `/api/v1/health` —
`worker_alive` should flip to `true`.

---

## 5. Vercel setup

Vercel serves the static React SPA. It does **not** run the API or worker; it
only hosts the pre-built `apps/web/dist/` output.

### 5.1 Create a project

1. Vercel dashboard → **Add New → Project** → import `Dueloro/moneymatch`.
2. Framework preset: **Vite**.
3. Root directory: **`apps/web`** — Vercel must only build the web app, not
   the API.
4. Build command: `pnpm --filter @moneymatch/web build` (or leave the default
   `vite build` since the root is already `apps/web`).
5. Output directory: `dist`.

### 5.2 Set environment variables on Vercel

Go to the project → **Settings → Environment Variables**. These are baked into
the browser bundle at build time.

**Required:**

| Key | Value |
| --- | --- |
| `VITE_API_BASE_URL` | Your Render API public URL, e.g. `https://moneymatch-api.onrender.com` |
| `VITE_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key — safe for the browser |

**Optional:**

| Key | Value |
| --- | --- |
| `VITE_POSTHOG_KEY` | Browser-side PostHog project key (different from the server-side API key) |
| `VITE_POSTHOG_HOST` | `https://us.i.posthog.com` |

> **Never** set `SUPABASE_JWT_SECRET`, `DATABASE_URL`, `FACEIT_API_KEY`, or any
> `SENTRY_DSN` on Vercel. Those are server secrets. Anything on Vercel is
> visible to every visitor who opens DevTools.

### 5.3 Deploy

After setting env vars, trigger a deployment (Vercel usually deploys on the
first import automatically). The build runs `pnpm install && pnpm build`; it
should take ~1-2 minutes. The SPA rewrite in `apps/web/vercel.json` routes all
paths to `/index.html` so React Router handles navigation client-side.

### 5.4 Verify the web app

Open your Vercel URL. You should see the sign-in page. Try creating an account
with email — Supabase sends a confirmation email (if you left email confirm on).
After confirming, you land in the app and the wallet shows $0 demo balance.

---

## 6. Post-deploy wiring

After both Render and Vercel are live, a few cross-service connections need to
be made:

### 6.1 Add Vercel URL to Supabase redirect allow-list

Go to Supabase → **Authentication → URL Configuration**:

- Set **Site URL** to `https://moneymatch-beta.vercel.app` (replace with your
  actual Vercel URL).
- Add it to **Redirect URLs** as well.

Without this, email confirmation links and OAuth callbacks return a 403 from Supabase.

### 6.2 Add Vercel URL to Render CORS allow-list

If your Vercel deployment URL changed from what you put in `WEB_ORIGIN`, update
the env var on the Render API service. Changes take effect on the next deploy
(Render restarts the service when env vars change).

### 6.3 Add custom domain (optional)

- **Vercel** — Settings → Domains → add your domain; Vercel gives you DNS records.
- **Render** — the API URL stays on `.onrender.com` unless you add a custom
  domain under Settings → Custom Domains.
- When you add a custom domain, update `WEB_ORIGIN` on Render and the Supabase
  redirect URLs to match.

---

## 7. Seed data for internal beta

The `scripts/seed_demo.py` script creates a small cohort of accounts with linked
game profiles and demo wallet balances, so testers have something to work with
immediately.

Run it against the production database once, after the first deploy:

```bash
# From the repo root, targeting the live DB:
export DATABASE_URL="postgresql+asyncpg://..."   # your Render internal URL
export SUPABASE_URL="https://..."
export SUPABASE_JWT_SECRET="..."
cd apps/api
uv run python scripts/seed_demo.py
```

The script is idempotent — running it twice will not create duplicate records.

---

## 8. Smoke checklist

Run through this after every first deploy and after any major release:

- [ ] `GET /api/v1/health` → `status: ok`, `worker_alive: true`
- [ ] Sign up with a new email account on the web app
- [ ] Email confirmation arrives and works (if confirm is on)
- [ ] Sign in → wallet shows demo balance of $0
- [ ] Wallet → Add funds → select $25 → balance updates to $25.00
- [ ] Link a Chess (Lichess) account by username → profile renders
- [ ] Admin panel (`/admin`) loads (log in as an admin-role user)
- [ ] Admin → Reconciliation → shows green (no violations)
- [ ] Admin → Flags → `settlement_paused` is off, `queue_paused` is off
- [ ] Open two browser sessions (two accounts), both join the same market queue
  → they match (may take a few seconds)
- [ ] Both accounts confirm the match → status moves to ACTIVE
- [ ] Worker heartbeat in `/health` stays fresh (< 120 s old) over 2+ minutes

---

## 9. Ongoing operations

See [`docs/runbook.md`](../runbook.md) for:

- How to restart the worker
- How to trigger a re-settle on a stuck match
- How to pause the queue or settlement via kill switches
- How to roll back a bad deploy
- How to restore from a Postgres point-in-time backup

Key admin endpoints available without a code deploy:

| What | Endpoint |
| --- | --- |
| Pause all settlement | `PUT /api/v1/admin/flags/settlement_paused` → `{"enabled": true}` |
| Pause matchmaking | `PUT /api/v1/admin/flags/queue_paused` → `{"enabled": true}` |
| Disable CS2 contests | `PUT /api/v1/admin/flags/game:cs2.faceit` → `{"enabled": false}` |
| Force-resettle a match | `POST /api/v1/admin/matches/{id}/resettle` |
| Void a match (full refund) | `POST /api/v1/admin/matches/{id}/void` |
| Freeze a user | `POST /api/v1/admin/users/{id}/freeze` |

---

## 10. Environment variable reference (complete)

For convenience, the full list in one place. Copy from `.env.example` for local
development; set on Render/Vercel for production.

### Render (API + worker)

| Key | Required | Default | Description |
| --- | --- | --- | --- |
| `ENV` | yes | — | `local \| dev \| prod`. Controls log format and debug behavior. |
| `DATABASE_URL` | yes | — | `postgresql+asyncpg://user:pass@host/db`. Must use the asyncpg driver scheme. |
| `SUPABASE_URL` | yes | — | `https://<ref>.supabase.co` |
| `SUPABASE_JWT_SECRET` | yes* | — | JWT secret from Supabase → Settings → API. *One of this or `SUPABASE_JWKS_URL` required. |
| `SUPABASE_JWKS_URL` | yes* | `${SUPABASE_URL}/auth/v1/.well-known/jwks.json` | Alternative to JWT secret for RS256 verification. |
| `SUPABASE_JWT_AUDIENCE` | no | `authenticated` | Expected `aud` claim in the JWT. |
| `WEB_ORIGIN` | yes | — | Comma-separated browser origins for CORS. Include your Vercel URL. |
| `FACEIT_API_KEY` | yes | — | Server-side FaceIt API key. CS2 adapter non-functional without it. |
| `PAYMENTS_LIVE` | no | `false` | Never flip to true without a live PaymentProvider compiled in (raises on startup). |
| `KYC_LIVE` | no | `false` | Same guard as above. |
| `MAX_REQUEST_BYTES` | no | `65536` | 413 threshold in bytes. |
| `RATE_LIMIT_WRITES_PER_MINUTE` | no | `60` | Per-IP rate cap on write/auth endpoints. |
| `SENTRY_DSN` | no | — | Python Sentry DSN. Error tracking. |
| `RELEASE` | no | — | Git SHA. Tags Sentry events and PostHog captures. |
| `POSTHOG_API_KEY` | no | — | Server-side PostHog key. Empty = silent no-op. |
| `POSTHOG_HOST` | no | `https://us.i.posthog.com` | PostHog ingest host. |
| `SLOW_HOST_MS` | no | `2000` | Logs a warning when a host-API call (FaceIt/Lichess/OpenDota) exceeds this many ms. |

### Vercel (web only)

| Key | Required | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | yes | Full public URL of the Render API, e.g. `https://moneymatch-api.onrender.com` |
| `VITE_SUPABASE_URL` | yes | Same project URL as `SUPABASE_URL` on Render |
| `VITE_SUPABASE_ANON_KEY` | yes | Supabase publishable/anon key — safe for the browser |
| `VITE_POSTHOG_KEY` | no | Browser-side PostHog project key (different from server key) |
| `VITE_POSTHOG_HOST` | no | PostHog ingest host, default `https://us.i.posthog.com` |
