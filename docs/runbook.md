# MoneyMatch Runbook

Operational reference for the MoneyMatch MVP (Phase 7 · `10-phase-7-hardening-beta.md`
§4). Written to be followed by someone who did **not** build the system — if a
step here is ambiguous, that is a bug in the runbook; fix it.

The one rule that overrides everything below: **the ledger is the source of
truth, and `sum(payouts) + rake == sum(entries)` must hold on every settlement
path.** When in doubt, pause settlement and investigate rather than push money.

---

## 1. Topology

| Component | Runs as | Host | Notes |
| --- | --- | --- | --- |
| `api` | long-running FastAPI (uvicorn) | Render web service | stateless; scale horizontally |
| `worker` | settlement worker loop | Render background worker | **single writer of settlements**; same image, worker entrypoint |
| Postgres 16 | managed DB | Render Postgres / Neon | ledger + queue; PITR enabled |
| `web` | static React (Vite) | Vercel | `apps/web/vercel.json` (SPA rewrite + security headers) |
| Auth | Supabase (email + Google) | Supabase | API verifies JWT; owns all other state |

Blueprint: [`render.yaml`](../render.yaml). Every env var is documented in
[`.env.example`](../.env.example); `config.py` fails fast on a missing one, so a
misconfigured deploy never boots half-working.

Environments: **staging** (full stack, host APIs live, seed cohort) and
**production**. Promote staging → production only after the acceptance
walk-through ([`12-mvp-acceptance.md`](./implementation-guide/12-mvp-acceptance.md)).

---

## 2. Deploy

Migrations run as a **release step**, never at import time.

1. Merge to `main` (squash). CI must be green (ruff · mypy · pytest · eslint ·
   tsc · vitest · build · pip-audit · pnpm audit).
2. Deploy triggers on Render. The `api` service's `preDeployCommand` runs
   `uv run alembic upgrade head` **once** before new instances take traffic.
   The worker never runs migrations.
3. Vercel builds `apps/web` from the same commit.
4. Set `RELEASE` to the git SHA so Sentry + PostHog tag events to the build.
5. Smoke: `GET /api/v1/health` returns `ok` and a fresh worker heartbeat; sign
   in on web; check the admin reconciliation view is green.

### Migrations

- Forward-only Alembic revisions; every schema change ships its migration in the
  same PR. Never edit a shipped revision.
- Verify locally before merge: `uv run alembic upgrade head && uv run alembic check`
  (drift check must report "No new upgrade operations").

---

## 3. Rollback

A bad release: redeploy the previous image from the Render dashboard (both `api`
and `worker`). Vercel: promote the previous deployment.

**Migrations are the caveat.** A forward migration that a rollback would strand
must be backward-compatible (additive) — that is why schema changes are additive
and shipped ahead of the code that needs them. If a deploy included a
destructive migration, do **not** roll back blindly: pause settlement (§5.3),
restore from PITR to just before the migration (§6), then redeploy.

---

## 4. Worker operations

The worker polls Postgres every ~15 s, claiming each unit of work with
`FOR UPDATE SKIP LOCKED` in its own transaction. A crash between claim and commit
leaves the row **re-claimable** — settlement is idempotent and never double-pays
(proven: `tests/test_chaos_resilience.py`).

- **Restart:** restart the Render worker service. No coordination needed; in-flight
  rows were never half-settled. Multiple workers are safe (SKIP LOCKED).
- **Heartbeat:** the worker writes `feature_flags.worker_heartbeat` each cycle.
  `GET /api/v1/health` and the admin reconciliation view redden when it is stale
  (> 120 s). A stale heartbeat = the worker is down or wedged → restart it.
- **Never** run a second worker as a one-off script against prod without
  understanding SKIP LOCKED; it is safe, but the ops signal (heartbeat) comes
  from the managed process.

---

## 5. Common incidents

### 5.1 Stuck match (won't settle)

Symptom: a match sits in `ACTIVE`/`AWAITING_RESULT` past its window; a user asks
where their money is.

1. Open the contest in admin: `GET /api/v1/admin/contests/match/{id}` — inspect
   the ledger trail + reconciliation for that ref.
2. If the host result is now available and the worker missed it, force a
   re-settle: `POST /api/v1/admin/matches/{id}/resettle`. This re-runs the exact
   worker grade+settle path (no bespoke money math) and is audited.
3. If the game genuinely never happened (host outage through the window), the
   worker cancels + refunds at the hard ceiling automatically. To resolve sooner,
   void with refund: `POST /api/v1/admin/matches/{id}/void`. Refunds rake nothing.
4. Confirm the contest reconciles green afterward.

### 5.2 Host API down (FaceIt / Lichess / OpenDota)

Symptom: settlement latency climbing; worker logs `HostUnavailable`.

- The worker already **extends** each affected match's window (outage never
  consumes it) and cancels + refunds at the hard ceiling — no money is stranded.
- To stop *new* contests on the affected game while the host is down, flip its
  per-game kill switch: `PUT /api/v1/admin/flags/game:<game_id>` → `enabled:false`
  (e.g. `game:cs2.faceit`). Takes effect on the next request, no deploy.
- Re-enable when the host recovers. Backfill settles automatically as results
  become available.

### 5.3 Reconciliation failure (hard stop)

Symptom: the worker hit a `ReconciliationError` and **set `settlement_paused` and
stopped** (fail-closed), or the admin reconciliation view shows a violation.

This is the one page-someone incident. **Do not clear `settlement_paused` to make
it go away.**

1. Leave settlement paused. Money is frozen, which is the safe state.
2. Open the admin reconciliation view: identify the offending ref
   (`solvency_violations` / `contest_violations`).
3. Reconstruct the ref's money trail event-by-event from the ledger in the admin
   contest detail. A settled contest must satisfy `sum(payouts) + rake ==
   sum(entries)`.
4. Root-cause before resuming. Only once the book is proven consistent (or the
   bad ref is corrected via an audited admin adjustment) clear the flag:
   `PUT /api/v1/admin/flags/settlement_paused` → `enabled:false`.

### 5.4 Queue misbehaving / abuse

- Pause matchmaking: `PUT /api/v1/admin/flags/queue_paused` → `enabled:true`. The
  worker then drains waiting tickets into clean cancels (no escrow was held).
- Freeze a specific user: `POST /api/v1/admin/users/{id}/freeze` (audited);
  a frozen user cannot stake. Unfreeze with `/unfreeze`.

---

## 6. Backup & restore

- Postgres runs on a PITR-capable plan (Render Postgres standard / Neon). Point-
  in-time restore is the primary recovery tool.
- **Restore procedure:** pause settlement (§5.3) → provision a restore to the
  target timestamp → repoint `DATABASE_URL` (or promote the restored branch) →
  run `alembic upgrade head` if the restore predates the current schema →
  verify reconciliation is green → resume settlement.
- Test a restore once before production launch and record the wall-clock time.
- The ledger is append-only (DB triggers enforce immutability), so a restore
  reproduces the exact money history — no derived-balance drift.

---

## 7. On-call basics

- **Dashboards:** Sentry (api + web errors), PostHog (funnel + liquidity), the
  admin reconciliation + risk views.
- **First checks for any money incident:** (1) worker heartbeat fresh? (2)
  reconciliation green? (3) `settlement_paused` off? If reconciliation is red,
  go to §5.3 and stop.
- **Escalation:** a reconciliation violation is a hard stop — keep settlement
  paused and escalate rather than guessing.

### Error budget (beta)

- Reconciliation violations: **0** (hard stop — any violation halts settlement).
- Settlement latency: **p95 < 2 min** from host-result availability.
- API latency under ~50 concurrent users: **p95 < 300 ms** (load sanity —
  [`load/`](../load/)).

---

## 8. Kill-switch reference

Flags live in the `feature_flags` table, flipped via `PUT /api/v1/admin/flags/{key}`
with no deploy. They take effect on the next request/cycle.

| Key | Effect |
| --- | --- |
| `settlement_paused` | Worker idles; no settlements commit (fail-closed). |
| `queue_paused` | Matchmaking off; worker drains waiting tickets to cancels. |
| `game:<game_id>` | Per-game enable (e.g. `game:cs2.faceit`). False ⇒ no new contests on that game. |

Real payment/KYC rails have **no** admin flag: `payments_live` / `kyc_live` are
config + code guarded (a flip alone is inert), so they can never be enabled by
an operator by accident.
