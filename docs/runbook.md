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

## First-time Render setup

1. Render → New → Blueprint → pick this repo. It reads `render.yaml`.
2. Fill the `sync: false` secrets **for each service** (API and worker each
   have their own list): `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (empty to use
   JWKS), `WEB_ORIGIN` (exact Vercel origin, no trailing slash), `SENTRY_DSN`,
   `POSTHOG_API_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `VAPID_PUBLIC_KEY`,
   `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`. `DATABASE_URL` is wired from the
   database automatically. Edit later in each service's Environment tab.
3. Region: every service and the database must be in the same region as the
   Supabase project (`ohio` in `render.yaml`). Change all of them together.
4. Custom domain: in your DNS, add a CNAME `api` → the API service's
   `*.onrender.com` host. Render issues the certificate once it resolves.
5. Vercel: set `VITE_API_BASE_URL=https://api.dueloro.com` plus the
   `VITE_SUPABASE_*`, `VITE_POSTHOG_*`, `VITE_SENTRY_DSN` values. If the API or
   Supabase host changes, update `connect-src` in `apps/web/vercel.json`.

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

- Render: each service → Events → pick the last good deploy → Rollback. Do the
  API and the worker.
- Vercel: promote the previous deployment.
- Migrations don't roll back. Keep schema changes additive so old code still
  runs on the new schema. If a deploy ran a destructive migration, pause
  settlement first and restore the database with Render's point-in-time
  recovery instead of rolling back blindly.

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
Flags tab. Takes effect on the next request or cycle, no deploy.

| Flag | Effect |
|---|---|
| `settlement_paused` | Worker settles nothing (heartbeat continues) |
| `queue_paused` | No new queueing; the worker cancels waiting tickets (no escrow is held) |
| `game:chess.lichess` | Off = no new chess contests |
| `geo_config` | Payload `excluded_states` lists blocked states |

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
