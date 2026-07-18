# Load sanity

Phase-7 load-sanity harness (`10-phase-7-hardening-beta.md` §2). Drives ~50
concurrent users through the synchronous money path (markets → queue → confirm)
against a **staging** deployment and asserts the bar:

- `http_req_duration` **p95 < 300 ms**
- zero failed invariant-touching writes
- reconciliation shows **0 violations** afterward (`sum(payouts) + rake ==
sum(entries)` held under load)

This is a manual, pre-release check — **not** gated in CI (it needs a live
staging env and real host APIs).

## Prerequisites

- [k6](https://k6.io/docs/get-started/installation/) installed.
- A staging deployment (`api` + `worker` + Postgres) seeded via
  `scripts/seed_demo.py`.
- One Supabase JWT per virtual user. Until the dev/e2e sign-in bypass lands
  (see `docs/implementation-guide/BACKLOG.md` · "Browser e2e test-auth seam"),
  mint these out of band from the staging Supabase project.

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

Also confirm the worker kept up: settlement latency **p95 < 2 min** from host
result availability (§4 error budget), visible in the admin reconciliation /
worker-heartbeat surface.
