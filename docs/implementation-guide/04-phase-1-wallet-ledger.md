# Phase 1 — Wallet & Ledger Core

**Objective:** server-authoritative money. Append-only ledger, derived balances,
demo deposits/withdrawals, limits — and the Wallet screen. This is the substrate
every settlement path writes to, and the future AML/audit trail; build it right once.

**Depends on:** Phase 0. **Unblocks:** Phases 3–7.

---

## Deliverables

1. Migrations: `wallets`, `ledger_entries` (+ append-only trigger blocking
   UPDATE/DELETE), `platform_ledger`, `limits` — shapes per `01-architecture.md` §2.
2. `wallet_service` (the **only** module that writes money):
   - `credit/debit`, `escrow_hold(user, amount, ref)`, `escrow_release`,
     `payout`, `rake`, `refund`, `demo_deposit`, `demo_withdrawal` — each writes
     a ledger row and updates the cached wallet balances **in one transaction**
     with `SELECT … FOR UPDATE` on the wallet row.
   - `assert_can_stake(user, amount_cents)`: available balance, daily loss cap,
     daily entry cap, concurrent-contest cap, `status=active`. Raises typed
     errors → RFC-7807 responses. (This buries the PoC's cosmetic
     `canJoin` loss-cap bug for good — enforcement is server-side only.)
3. New-user provisioning grants a `DEMO` wallet with a **$1,000.00 signup
   credit** as a ledger row (`demo_deposit`, memo "signup grant") — not a magic
   starting number. The grant is **funded from `platform:promo`** (chart of
   accounts, `01-architecture.md` §2) so demo money never appears from nowhere
   and the global solvency invariant
   `sum(user available + escrow) == promo funding − rake` holds at all times.
4. Endpoints: `GET /wallet`, `GET /wallet/ledger` (cursor-paginated),
   `POST /wallet/demo-deposit` (presets $10/$25/$50/$100 only, server-defined),
   `POST /wallet/demo-withdrawal` (≤ available; velocity-capped at 5/day).
5. Reconciliation: `reconciliation_service.check(ref)` asserting
   `sum(payouts) + rake == sum(entries)` per contest ref, plus a global
   `check_all()` that also asserts the **solvency invariant** across all
   wallets vs. `platform:promo`/`platform:rake` (used by the worker in Phase 3
   and admin in Phase 6).
6. **Wallet screen** (PDF p.10): Available / In escrow / Lifetime stat bar,
   Add-funds preset pills, Recent ledger list with signed amounts and relative
   time. Header balance component (used on Play) reads the same query.
7. Limits API: `PATCH /me` accepts lowering `daily_loss_cap` instantly; raising
   is recorded but takes effect after a 24 h cooldown (store
   `pending_limit`, `effective_at`). Self-exclusion endpoint freezes staking.

## Design rules (restated from `00-README.md` §3 — enforced here)

- Integer cents everywhere; API serializes cents, web formats via the ported
  `format.ts` (rewrite `formatCurrency` to take cents).
- `balance_after_cents` on every ledger row → any balance is re-derivable and
  any point-in-time statement is a range query.
- No endpoint accepts an arbitrary client amount except demo-withdrawal
  (bounded by available); deposits are presets.

## Reuse from `poc-reference/`

| What | From | Note |
| --- | --- | --- |
| Wallet bucket semantics (available/escrow) | `frontend/src/hooks/useWallet.ts` | semantics only; state moves server-side |
| Money invariant tests | `tests/test_tournament.py` (invariant patterns) | port the *assertions* against the new ledger |
| Currency formatting | `frontend/src/utils/format.ts` | adapt to cents |

## Tests required (this phase is test-heavy by design)

- Property-style: random sequences of holds/settles/refunds keep
  `available ≥ 0`, `escrow ≥ 0`, ledger sum == cached balance.
- Escrow/settle/refund each: ledger rows, balance cache, `balance_after` chain.
- Rounding: odd pots (e.g. 3 × $3.33) — payouts + rake reconcile exactly,
  remainder cents land in rake.
- Limits: loss cap blocks at the boundary; entry cap; concurrent cap; frozen /
  self-excluded users blocked; cooldown on raising limits.
- Append-only trigger: UPDATE/DELETE on `ledger_entries` fails at the DB level.
- Concurrency: two parallel escrows against a balance that covers only one —
  exactly one succeeds (needs the FOR UPDATE test harness).

## Exit criteria

- [ ] Wallet screen matches PDF p.10 with live data; add-funds and withdrawal
      round-trip through real ledger rows.
- [ ] `check_all()` passes after a scripted storm of concurrent demo operations.
- [ ] A hand-crafted request cannot mint money (attempt: negative amounts,
      non-preset deposits, double-spend race) — covered by tests.
- [ ] Balances identical across two browsers/devices for the same account.
