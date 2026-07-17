# MVP Acceptance Checklist

The definition of done for the MoneyMatch MVP. Every box gets checked by a
tester who is **not** the implementer, on the staging deployment, during the
Phase-7 internal beta. Line items map to the user-stated MVP criteria plus the
integrity/ops bars the docs establish.

## A. Accounts & identity

- [ ] Sign up with email and with Google; onboarding sets username, state, 18+ attestation.
- [ ] Sessions persist; sign-out/in works; a second device sees identical state.
- [ ] Link real Lichess, FaceIt, and OpenDota accounts; profiles show correct stats.
- [ ] An already-bound host account cannot be linked by a second user.
- [ ] Self-exclusion immediately blocks all staking.

## B. Core challenge flow (end-to-end)

- [ ] Two real users on separate machines: queue on the same market/entry →
      matched → both confirm (escrow visible in both wallets) → play →
      settlement lands with **no manual steps**.
- [ ] Chess brokered flow: both players receive playable game URLs; the played
      game between the bound accounts settles the match.
- [ ] CS2 stat race (K/D, ADR, HS%) and win-your-next resolve from real FaceIt
      data; equal stats / both-win → push (full refund, no rake).
- [ ] Friend challenge and invite link both produce a settled match; the invite
      link works for a brand-new user (signup mid-flow).
- [ ] Unfilled window (no qualifying game in 24 h) → automatic cancel + refund.

## C. Verification & settlement (integrity)

- [ ] 100% of settlements are host-API-verified; there is no self-report
      control anywhere in UI or API.
- [ ] `sum(payouts) + rake == sum(entries)` holds for every settled ref in the
      reconciliation view after the beta week (violations = 0).
- [ ] A tampered client cannot alter any amount, timestamp, or result
      (attempts from the Phase-7 IDOR/abuse test matrix all rejected).
- [ ] Any settled contest's money trail reconstructs event-by-event from the
      ledger in the admin UI.
- [ ] Settlement latency p95 < 2 min from host-result availability.

## D. Money (demo)

- [ ] Demo deposits and withdrawals work through real ledger rows; Wallet
      screen matches balances exactly across devices.
- [ ] Daily loss cap, daily entry cap, and concurrent-contest cap enforce
      server-side at the boundary; lowering limits is instant, raising is delayed 24 h.
- [ ] Geo-fence: a user in an excluded state is blocked at entry, before escrow.
- [ ] Rake appears pre-commit on every slip; refunds/pushes rake nothing.

## E. Pools & tournaments

- [ ] Enter a CS2 pool queue; difficulty bars are quoted from your own
      baseline; a room forms whose bar equals the rounded mean of members'
      personal bars (shown with your delta); server-fetched telemetry grades
      it; clearers split the pool minus rake; nobody-clears → full refund.
- [ ] The composition predicate verifiably refuses an unfair room (shark /
      outlier fixtures), and the tournament dispersion cap refuses a lopsided
      field; no API accepts a user-supplied bar, room bar, or payout number.
- [ ] Room bars and pairings replay deterministically from frozen baseline
      snapshots (audit re-run on a settled room matches byte-for-byte).
- [ ] A matchmade tournament runs a full window with live standings, first-N
      scoring, and exact 50/30/20 payouts (tie case exercised);
      under-min-field/`min_ranked` paths cancel with refunds.
- [ ] Pool multiplier copy says "estimated"; payout equals share-of-pool.

## F. UI quality

- [ ] Every screen matches `docs/design/moneymatch-design.pdf` (Play slip
      states, Pools tiers, Tournament cards/standings, Activity, Wallet,
      Inbox, Friends, Leaderboard, Profile, Sign-in).
- [ ] Empty, loading, and error states exist on every list; no blank panels.
- [ ] A non-team member can complete signup → link → first contest without help
      (hallway test, ≥2 people).

## G. Admin & ops

- [ ] Admin can find any user/contest, inspect its ledger, freeze a user,
      re-settle and void a match — each action audited.
- [ ] Kill switches (per-game, queue, settlement) take effect without deploy.
- [ ] Worker heartbeat visible; killing the worker mid-cycle loses nothing and
      double-pays nothing (chaos test).
- [ ] Seed script stands up a demoable environment in one command.
- [ ] PostHog dashboards show the activation funnel and liquidity metrics for
      the beta week.

## H. Payments/KYC readiness (not integration)

- [ ] `PaymentProvider` / `KycProvider` protocols exist; demo provider is the
      only implementation; `payments_live`/`kyc_live` flags are false and
      guarded in code.
- [ ] `kyc_status` and cap-config plumbing exist and are exercised by tests.

## I. Engineering health

- [ ] CI green: ruff, mypy, eslint, tsc, pytest, vitest on PRs; Playwright e2e nightly.
- [ ] Staging + production deploys documented; rollback tested once.
- [ ] `docs/runbook.md` validated by a non-author.
- [ ] No secrets in repo; `.env.example` complete; dependency audits clean.
