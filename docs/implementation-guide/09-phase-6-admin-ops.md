# Phase 6 — Admin Tools & Instrumentation

**Objective:** the operator surface ("basic admin tools exist" MVP criterion)
and real product analytics. An internal beta without these is unsupportable —
someone must be able to inspect a stuck match, refund a user, and flip a kill
switch without a deploy.

**Depends on:** Phases 1–5 (admin reads all of it). Can start once Phase 3 lands.

---

## Deliverables

1. **Admin access model:** `users.role = admin` (set via a
   `scripts/grant_admin.py` script, audited). All `/admin/*` routers require it.
   **Every admin mutation writes `admin_audit`** — no exceptions.
2. **Admin UI** — a separate route tree in the same web app (`/admin`), plain
   functional tables (this does *not* follow the consumer design system; keep
   it dense and boring):
   - **Users:** search, detail (wallet, ledger, linked accounts, limits,
     contests), actions: freeze/unfreeze, force-unbind a linked account,
     manual ledger adjustment (reason required; ledger `adjustment` type).
   - **Contests:** matches/pools/tournaments by state + game; detail shows the
     full lifecycle + ledger rows + adapter evidence (`outcome_detail`);
     actions: force re-settle (re-runs the worker path), void → refund.
   - **Queue:** live tickets, depth per (game, market, tier), average wait,
     expiry rate.
   - **Flags:** toggle per-game enable, `queue_paused`, `settlement_paused`;
     edit `geo_config` state list.
   - **Reconciliation:** `check_all()` on demand (per-contest conservation +
     global solvency) + last worker-run status; any violating ref renders red
     with its ledger trail.
   - **Risk view** (from the challenge-engine proposal §11/§15): per
     (game, market/difficulty) — offered/accepted counts, **actual vs.
     expected clear/win rates** (pools should track their `p_target`; duels
     should sit near 50%), rake accrued, dispute count; alert rows when a rate
     drifts beyond a threshold (a mispriced `k` or a systematic exploit looks
     identical from here). Plus the flag queue: sandbagging flags (Phase 4
     detector), abnormal win streaks, pair-cap breaches — each with
     freeze/clear actions. Rule from the proposal, kept verbatim: risk
     responses may adjust **future** formation/generation, never an accepted
     in-flight contest.
3. **Analytics (PostHog):**
   - Web: point the PoC's `track()` seam (`poc-reference/frontend/src/utils/telemetry.ts`
     event names — keep them stable) at PostHog; identify by user id after auth.
   - Server: PostHog server-side capture for money/liquidity events
     (`entry_queued`, `match_found`, `contest_settled`, `rake_collected`,
     `refund_issued`) — client-only analytics can't see the worker.
   - The activation funnel from `docs/business/gtm-prelaunch.md` §1.2
     (`landing → signup → account_linked → first_contest_joined →
     first_settlement`) instrumented end-to-end; build the funnel + liquidity
     dashboards in PostHog and link them in the repo README.
4. **Ops hygiene:** Sentry release tagging; structured request logs with user
   id; slow-host-API warnings; a `/api/v1/health` extension reporting worker
   heartbeat (worker writes `feature_flags.worker_heartbeat` each cycle; health
   reddens if stale > 2 min).
5. **Seed script** (`scripts/seed_demo.py`): N demo users with wallets, linked
   fixture accounts, open tickets, rooms, a tournament — one command to make a
   fresh environment demoable. Used by e2e too.

## Tests required

- AuthZ: non-admin gets 403 on every `/admin/*` route (parametrized test).
- Audit: each admin action writes an `admin_audit` row (parametrized).
- Re-settle: idempotent (running twice doesn't double-pay — the ledger service
  must reject a second payout for the same ref).
- Void: refunds exactly the escrowed amounts, invariant holds.
- Flag flips take effect without restart (config read path is per-request/cycle).

## Exit criteria

- [x] An operator can find any user/contest, see its complete money trail, and
      fix a stuck or wrong settlement — all in the UI, all audited.
      _Evidence: `/admin/users` (search → detail: wallet, ledger, linked, limits,
      contests) + `/admin/contests` detail (participants, user + platform ledger,
      adapter evidence, live reconciliation). Fixes: `resettle` (idempotent) and
      `void` (exact refund). Tests: `test_admin_users.py`, `test_admin_contests.py`
      (`test_resettle_is_idempotent`, `test_void_refunds_exactly_and_reconciles`),
      audit rows asserted throughout; `test_admin_authz.py` gates every route._
- [x] `settlement_paused` + `queue_paused` verifiably stop the machinery.
      _Evidence: `PUT /admin/flags/{key}` flips are read per-request/cycle
      (`test_admin_flags.py::test_toggle_takes_effect_without_restart`); the worker
      honors both (`test_settlement_worker.py::test_settlement_paused_halts_the_loop`,
      `::test_queue_paused_drains_waiting_tickets`)._
- [~] PostHog shows a complete funnel for a fresh demo user session.
      _Instrumented end-to-end: server capture seam emits `entry_queued`,
      `match_found`, `contest_settled`, `rake_collected`, `refund_issued`
      (`test_analytics.py`); the client sink + `identify` carry the activation
      funnel names (`landing → signup → account_linked → first_contest_joined →
      first_settlement`). The PostHog dashboards themselves are built in the
      PostHog UI and verified live during the Phase-7 beta (README has the links;
      backlog note)._
- [x] `scripts/seed_demo.py` produces a demoable environment in one command.
      _Evidence: `make seed` / `uv run python scripts/seed_demo.py` — admin +
      N players (wallets, linked CS2 fixtures, non-provisional metrics), open
      tickets, an escrowed pool, a tournament; idempotent + solvency-clean on
      re-run (verified: `check_all` ok, 0 contest breaches)._

Also delivered: ops hygiene — request-log middleware with user id + request id,
slow-host-API warnings, Sentry release tagging, worker heartbeat
(`feature_flags.worker_heartbeat`) surfaced on `/health` and the admin
Reconciliation tab (reddens > 2 min stale; `test_worker_heartbeat.py`).
