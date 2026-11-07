# Load sanity

Load-sanity harness. Drives ~50 concurrent users through chess head-to-head (markets → queue →
confirm, blitz at $10) against a **staging** deployment. k6 enforces:

- `http_req_duration` **p95 < 300 ms**
- zero failed queue writes (`write_errors` rate 0)
- checks pass rate above 99%

By hand afterward: reconciliation shows **0 violations** afterward (`sum(payouts) + rake ==
sum(entries)` held under load)

This is a manual, pre-release check — **not** gated in CI (it needs a live
staging env and real host APIs).

## Prerequisites

- [k6](https://k6.io/docs/get-started/installation/) installed.
- A staging deployment (`api` + `worker` + Postgres) with at least 50 onboarded
  users, each with a linked Lichess account. Their ratings must be close enough to
  pair within the Elo band (starts at ±100, widens 12/s to ±800).
- One Supabase JWT per virtual user, minted out of band from the staging
  Supabase project (or via `POST /api/v1/dev/e2e/token` on a non-prod stack
  with `E2E_AUTH_ENABLED=true`).

## Run

```bash
BASE_URL=https://staging-api.moneymatch.example \
TOKENS='["<jwt-user-1>","<jwt-user-2>", ... 50 tokens]' \
k6 run load/queue-confirm-settle.js
```

k6 exits non-zero if any threshold is breached.

## After the run

Pull the reconciliation view with an admin token and confirm zero violations:

```bash
curl -sH "Authorization: Bearer <admin-jwt>" \
  "$BASE_URL/api/v1/admin/reconciliation" | jq '{ok, solvency_violations, contest_violations}'
# => { "ok": true, "solvency_violations": [], "contest_violations": [] }
```

Also confirm the worker kept up: `GET /api/v1/health` shows `worker.stale: false`.
