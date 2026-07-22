# End-to-end tests (Playwright)

`h2h.spec.ts` drives the Phase-3 exit criterion: two users complete
queue → match → confirm → play → auto-settlement, and the money lands exactly
(winner **+$18.00**, loser **−$10.00**, **$2.00** rake).

`pools.spec.ts` drives the Phase-4 exit criterion: four similar-stat users pick
Medium, enqueue, form a room whose `room_bar` is the rounded mean of their bars,
clear a (fixture) match, and split the pool from server-fetched telemetry — zero
client input after enqueue.

`invite.spec.ts` drives the Phase-5 funnel: A mints an invite link, a **fresh**
user B accepts, both confirm, the fixture settles, and both inboxes are correct.

All three **skip** unless `E2E_AUTH=1` (they never silently pass). This suite is
**not** in the unit-test CI job — it needs the whole stack and real browsers.

## The test-auth seam

Auth is Supabase-JWT, but the specs no longer need a live Supabase project. The
seam (backlog · resolved) has two halves:

- **API** — with `E2E_AUTH_ENABLED=true` (and `env != prod`), the route
  `POST /api/v1/dev/e2e/token {auth_id, email?}` mints a short-lived HS256 JWT
  signed with `SUPABASE_JWT_SECRET`. It is verified by the exact same
  `auth.verify_token` path as a real token — the auth boundary is unchanged.
- **web** — built with `VITE_E2E_AUTH=true`, the app reads an access token from
  the `mm.e2e.access_token` localStorage key instead of a Supabase session
  (`src/lib/e2eAuth.ts`). Inert in a normal build.

`e2e/auth.ts` ties them together: `signInAs(browser, authId)` mints a token for a
seeded user and injects it into a fresh context.

## Prerequisites

1. **Stack up with the seam on:**
   ```bash
   E2E_AUTH_ENABLED=true make dev    # api mints tokens; web built with VITE_E2E_AUTH=true
   ```
2. **Seed the cohort:** `make seed` — creates `seed_player1…N` (CS2-linked,
   non-provisional). The specs default to these `auth_id`s.
3. **Stubbed host adapter:** the settlement worker must grade each account's next
   CS2 match deterministically (a fixture FaceIt response), so contests resolve
   without a real game.
4. **Run:**
   ```bash
   E2E_AUTH=1 make e2e
   ```

Overrides (all optional): `E2E_AUTH_ID_A` / `E2E_AUTH_ID_B` (h2h + invite
challenger), `E2E_POOL_AUTH_IDS` (JSON array), `E2E_FRESH_AUTH_ID` (invite's
fresh signup), `E2E_API_BASE_URL` (default `http://localhost:8000`).

The exact settlement money math is also proven executably by the API/worker suite
(`apps/api/tests/test_settlement_worker.py` ·
`test_stat_race_win_pays_winner_and_reconciles`: winner 10800, loser 9000,
rake 200 — i.e. +$18 / −$10 / $2 — with the conservation invariant asserted).
