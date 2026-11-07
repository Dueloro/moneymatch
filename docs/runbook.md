# Runbook

Operating Money Match in production. The rule above all others: the ledger is
the source of truth. If money looks wrong, pause settlement and investigate.
Don't push money through.

## Topology

| Piece | Where | Defined in |
|---|---|---|
| API (`moneymatch-api`) | Render web service, `api.dueloro.com` | `render.yaml` |
| Worker (`moneymatch-worker`) | Render background worker, same image | `render.yaml` |
| Postgres 16 (`moneymatch-postgres`) | Render Postgres | `render.yaml` |
| Web | Vercel, builds `apps/web` | `apps/web/vercel.json` |
| Auth | Supabase | Supabase dashboard |

Admin endpoints below are under `/api/v1/admin` and need an admin user's
token. The `/admin` web pages call the same endpoints.

## First-time setup

Order: Vercel project, Render Blueprint, custom domain, first admin. `WEB_ORIGIN`
is entered at Blueprint creation and must be the exact Vercel production
origin; the API refuses to boot in prod if it is localhost.

### 1. Vercel project

- Root Directory `apps/web`, Framework Preset Vite. Keep "Include files outside
  the root directory" on (the `packages/api-client` workspace dep needs it).
- Env vars: `VITE_API_BASE_URL=https://api.dueloro.com`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY` (all required), optional `VITE_POSTHOG_*` and
  `VITE_SENTRY_DSN`. Never set `VITE_E2E_AUTH` in prod.
- The CSP in `apps/web/vercel.json` hardcodes `https://api.dueloro.com` and the
  Supabase project `bxjzxvujyveucyfvmmto`. If your Supabase project differs,
  update `connect-src` first or auth calls are blocked.

### 2. Render Blueprint

1. Render → New → Blueprint → pick this repo. It reads `render.yaml`.
2. `sync: false` secrets are prompted only at creation, per service (give the
   API and the worker the same values): `SUPABASE_URL`, `SUPABASE_JWT_SECRET`,
   `WEB_ORIGIN`, `SENTRY_DSN`, `POSTHOG_API_KEY`, `RESEND_API_KEY`,
   `EMAIL_FROM`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`.
   `DATABASE_URL` is wired from the database. Edit later in each service's
   Environment tab.
   - `SUPABASE_URL` and a non-localhost `WEB_ORIGIN` are required on both.
   - `EMAIL_FROM` = `Money Match <noreply@send.dueloro.com>`.
   - Blank `SUPABASE_JWT_SECRET` means verify via JWKS. Blank `SENTRY_DSN`,
     `POSTHOG_API_KEY` or `VAPID_*` just disables that feature.
3. Region: every service and the database must be in the same region as the
   Supabase project (`ohio` in `render.yaml`). Change all of them together.

### 3. Custom domain

API service → Settings → Custom Domains → add `api.dueloro.com`. At your DNS
provider add a CNAME `api` → the service's `*.onrender.com` host, then click
Verify and wait for the certificate. On Cloudflare, keep the record DNS-only
until the certificate is issued.

### 4. First admin

Sign up on the web app, then run the script under Granting admin against the
database's external URL (Render's default allow-list accepts external
connections). Rewrite the scheme to `postgresql+asyncpg://` and add
`?ssl=require`; `SUPABASE_URL` is required because the config loads on import.

### Google sign-in

The web offers Google via Supabase. Create a Google OAuth client with
authorized redirect `https://<supabase-ref>.supabase.co/auth/v1/callback`.
In Supabase enable Auth → Providers → Google with its client ID and secret,
and add the web origin under Auth → URL Configuration (Site URL and Redirect
URLs).

### Supabase email (via Resend)

Do these only after the sending domain (`send.dueloro.com`) shows Verified in
Resend. An unverified domain makes every auth email fail.

1. Auth → SMTP Settings → Custom SMTP: host `smtp.resend.com`, port `465`,
   user `resend`, password a Resend API key, sender `Money Match`
   `<noreply@send.dueloro.com>`.
2. Auth → Providers → Email: enable Confirm email; keep email OTP on.
3. Auth → URL Configuration: Site URL = the web origin; add
   `<web origin>/**` and `http://localhost:5173/**` to Redirect URLs.
4. Auth → Email Templates: paste `supabase/email-templates/confirm-signup.html`,
   `magic-link.html` (must keep `{{ .Token }}`), `reset-password.html`.
5. Sign up with a real address and check the verify, code and reset emails.

## Deploy

Push or merge to `main`. CI runs; Render auto-deploys both services
(`autoDeployTrigger: commit`) and Vercel builds the web app from the same
commit. After deploy:

- `GET https://api.dueloro.com/api/v1/health` returns `status: ok` and
  `worker.stale: false`.
- Sign in on the web app; the admin Reconciliation tab is green.

## Migrations

The API's `preDeployCommand: alembic upgrade head` runs once per deploy before
the new instance takes traffic. A failure aborts the deploy. The worker never
migrates.

To run one by hand, copy the database's **External** URL from Render and run:

```bash
cd apps/api
DATABASE_URL='postgresql+asyncpg://USER:PASS@HOST/DB?ssl=require' \
SUPABASE_URL=https://<project>.supabase.co \
uv run alembic upgrade head
```

Change the scheme to `postgresql+asyncpg://` and add `?ssl=require` (asyncpg
needs it for external connections). `SUPABASE_URL` is required because the
config loads on import.

## Rollback

- Render: each service → Deploys → pick the last good deploy → Rollback →
  Rollback to this deploy. This turns off auto-deploy for that service;
  re-enable it in Settings once fixed. Roll back the API and the worker
  together.
- Vercel: Project → Instant Rollback → choose the deployment → Confirm. New
  pushes stop going live until you Undo Rollback (or promote a deployment).
  Hobby plans can only roll back to the previous deployment.
- Migrations don't roll back. Keep schema changes additive so old code still
  runs on the new schema. If a deploy ran a destructive migration, pause
  settlement first and restore the database with Render's point-in-time
  recovery instead of rolling back blindly.
- Point-in-time recovery: available on paid Render Postgres, 3-day window on
  Hobby workspaces and 7 days on Pro+; you can't restore to within the last 10
  minutes. It creates a NEW database, so set `DATABASE_URL` on the API and the
  worker to the new internal URL, and update `render.yaml`'s `fromDatabase`
  name so a Blueprint sync doesn't point back at the old DB.

## Worker health

- Each cycle (every 15 s) the worker writes the `worker_heartbeat` flag, even
  while settlement is paused.
- `GET /api/v1/health` reports `worker.heartbeat_at` and `worker.stale`
  (stale after 120 s). The admin Reconciliation tab shows the same.
- Stale: check the worker's logs in Render and restart it. Restarting is safe:
  work is claimed with `FOR UPDATE SKIP LOCKED` and settlement is idempotent.

## Reconciliation

- `GET /api/v1/admin/reconciliation` (or the admin Reconciliation tab) checks
  global solvency and every contest's `entries = payouts + refunds + rake`.
- After every settle the code checks that contest. A breach makes the worker
  set `settlement_paused` and stop.
- On a breach: **leave settlement paused.** Find the ref in
  `contest_violations`, read its ledger trail
  (`GET /api/v1/admin/contests/{ref_type}/{ref_id}`), and find the cause.
  Correct with an audited adjustment (`POST /api/v1/admin/users/{id}/adjust`)
  if needed. Resume only when reconciliation is green.

## Kill switches

`PUT /api/v1/admin/flags/{key}` with `{"enabled": true|false}`, or the admin
Flags tab. Takes effect on the next request or cycle, no deploy. The body takes
`enabled` and/or `payload`; for `geo_config`:
`{"payload": {"excluded_states": ["AZ", "AR", ...]}}`.

| Flag | Effect |
|---|---|
| `settlement_paused` | Worker settles nothing (heartbeat continues) |
| `queue_paused` | No new queueing; the worker cancels waiting tickets (no escrow is held) |
| `game:chess.lichess` | Off = no new chess contests |
| `geo_config` | Payload `excluded_states` lists blocked states |

In prod the API refuses to boot if `geo_config` excludes fewer than the 14
seeded states (`GEO_REQUIRED_EXCLUDED_STATES` in `constants.py`). You can add
states by flag, but un-excluding one is a code change and deploy (or setting
`GEO_ENFORCE_SEEDED_FLOOR=false` on both services, and recording why).

Real-money rails (`PAYMENTS_LIVE`, `KYC_LIVE`) are not flags. They are env
config plus code guards and stay off.

## Granting admin

```bash
cd apps/api
DATABASE_URL='postgresql+asyncpg://…?ssl=require' SUPABASE_URL=https://<project>.supabase.co \
  uv run python ../../scripts/grant_admin.py <username>          # add --revoke to remove
```

The change is written to `admin_audit`.

## Incidents

First checks for any money problem: is the worker heartbeat fresh, is
reconciliation green, is `settlement_paused` off?

- **Match won't settle.** Inspect it (`GET /api/v1/admin/contests/match/{id}`).
  If Lichess has the result, `POST /api/v1/admin/matches/{id}/resettle`
  (same grading path, audited). If the game never happened,
  `POST /api/v1/admin/matches/{id}/void` refunds both, no fee. Unattended, the
  worker cancels and refunds at the hard ceiling.
- **Lichess down.** The worker extends match windows and cancels with refunds
  past the ceiling. To stop new contests, turn `game:chess.lichess` off.
- **Abuse.** `POST /api/v1/admin/users/{id}/freeze` (and `/unfreeze`). Review
  the admin Risk tab. Pause the queue if needed.
- **Reconciliation breach.** See above. Keep settlement paused and escalate.

Dashboards: Sentry (API, worker, web errors), PostHog (funnel, money events),
Render logs, the admin Reconciliation and Risk tabs.
