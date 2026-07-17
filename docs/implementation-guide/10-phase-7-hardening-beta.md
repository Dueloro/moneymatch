# Phase 7 — Payments-Readiness, Hardening & Internal Beta

**Objective:** make the MVP launch-shaped: payments/KYC integration-ready (not
integrated), the full e2e suite, a polish pass against the design PDF, deploy,
and run the internal beta against the acceptance checklist
([`12-mvp-acceptance.md`](./12-mvp-acceptance.md)).

**Depends on:** everything.

---

## 1. Payments/KYC readiness (seams only — no processor)

Per `docs/legal/legal-compliance.md` §4–5, real rails are a Stage-C workstream
gated on counsel + underwriting. The MVP ships the **interfaces** so integration
is additive:

- `payments/` package with a `PaymentProvider` protocol
  (`create_deposit_intent`, `payout`, `webhook_event → ledger events`) and the
  single implementation `DemoProvider` (what Phase 1's demo rails call). The
  future Aeropay/Nuvei providers implement the same protocol.
- `kyc/` package with a `KycProvider` protocol (`start_verification`,
  `get_status`) + `users.kyc_status` column (`none|pending|verified|failed`,
  default `none`) and a `kyc_required(user, action)` policy hook that always
  returns `False` at MVP but is **called** at deposit/withdrawal/threshold
  sites so the call sites exist and are tested.
- Config-driven Phase-1 caps table (from `docs/product/overview.md` §7.3):
  min/max entry, daily caps, KYC threshold, withdrawal min — already enforced
  where applicable; the rest wired to the policy hook.
- Feature flags: `payments_live=false`, `kyc_live=false`. Turning them on must
  be a code + config change, never config alone (guard in code).

## 2. Hardening

- **Security pass:** authZ audit (every router requires auth; object-level
  checks — user A cannot read user B's match/wallet/notifications: write the
  IDOR test matrix); rate limits (slowapi or middleware) on auth-sensitive and
  write endpoints; input size caps; security headers on the web app
  (CSP, frame-ancestors); dependency audit (`pip-audit`, `pnpm audit`) in CI.
- **Resilience:** chaos-style tests — kill the worker mid-settlement (row must
  be re-claimable, never double-paid); host API outage during a settlement
  window (matches cancel + refund at window end); Postgres restart during
  queue activity.
- **Load sanity:** a locust/k6 script driving ~50 concurrent users through
  queue/confirm/settle against staging; no invariant violations, p95 API < 300 ms.
- **Full e2e suite (Playwright)** — the money paths as user journeys:
  signup → link → deposit → H2H win/lose/push; pool clear/miss/refund;
  tournament window; invite-link signup; admin void; self-exclusion actually
  blocks staking. Runs nightly + pre-release (host APIs fixture-mocked via a
  stub server).

## 3. Polish pass (UI acceptance)

Screen-by-screen against the PDF with `02-design-system.md` open: spacing,
type scale, green consistency, empty states for every list (no blank panels),
loading skeletons, error toasts with human copy, keyboard/focus states,
the footer breadcrumb on every screen. Fix copy: amounts always formatted from
cents; rake always visible pre-commit; "estimated" language on pool multipliers.

## 4. Deploy & runbook

- Staging + production environments (Railway/Render): `api`, `worker`,
  Postgres (Neon), web (Vercel). Migrations run as a release step
  (`alembic upgrade head`), never at import time.
- `docs/runbook.md`: deploy procedure, rollback, worker restart, common
  incidents (stuck match → admin re-settle; host API down → pause game flag;
  reconciliation failure → settlement_paused + investigate), backup/restore
  (Neon PITR), on-call basics.
- Error budget for beta: reconciliation violations = 0 (hard stop), settlement
  latency p95 < 2 min after host result availability.

## 5. Internal beta

- Seed the team (5–10 users) with real linked accounts; run ≥1 week.
- Weekly metrics snapshot (PostHog): activation funnel, contests/user,
  time-to-match, settlement latency, % host-verified (target 100%).
- Bug triage into `BACKLOG.md`; acceptance walk-through per
  [`12-mvp-acceptance.md`](./12-mvp-acceptance.md) — every box checked by a
  named person, not the implementer.

## Exit criteria

- [ ] Payments/KYC protocols exist with demo implementations + tests; caps
      config-driven; flags guard real rails.
- [ ] IDOR matrix, rate limits, and dependency audit green in CI.
- [ ] e2e suite green nightly; chaos tests pass (no double-pay, no stranded escrow).
- [ ] Staging + production deployed; runbook validated by someone who didn't
      write it.
- [ ] Internal beta week completed; acceptance checklist fully signed off.
