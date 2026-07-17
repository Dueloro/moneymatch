# End-to-end tests (Playwright)

`h2h.spec.ts` drives the Phase-3 exit criterion: two users complete
queue → match → confirm → play → auto-settlement, and the money lands exactly
(winner **+$18.00**, loser **−$10.00**, **$2.00** rake).

`pools.spec.ts` drives the Phase-4 exit criterion: four similar-stat users pick
Medium, enqueue, form a room whose `room_bar` is the rounded mean of their bars,
clear a (fixture) match, and split the pool from server-fetched telemetry — zero
client input after enqueue. It reads `E2E_POOL_USERS` (a JSON array of seeded,
CS2-linked sessions) and **skips** if unset.

This suite is **not** in the unit-test CI job — it needs the whole stack and real
browsers. Run it with `make e2e`.

## Prerequisites

1. **Stack up:** `make dev` (db + api + worker + web on :5173).
2. **Stubbed host adapter:** the settlement worker must grade the two accounts'
   next CS2 match deterministically (a fixture FaceIt response), so the duel
   resolves without a real game. Point `FACEIT_API_KEY` at the fixture server or
   inject a fake adapter for the e2e run.
3. **Two seeded, CS2-linked users with sessions.** Because auth is Supabase-JWT
   (the app persists only the session in `localStorage`), each browser context is
   authenticated by injecting a ready session:

   ```bash
   export E2E_USER_A='{"access_token":"…","refresh_token":"…", …}'
   export E2E_USER_B='{"access_token":"…","refresh_token":"…", …}'
   make e2e
   ```

   Without these env vars the spec **skips** (it never silently passes).

## Known gap (tracked in BACKLOG)

A first-class **test-auth seam** (a local sign-in bypass that mints a session for a
seeded user) is needed to run this in CI without a live Supabase project. Until
then, the exact settlement money math is proven executably by the API/worker
integration suite (`apps/api/tests/test_settlement_worker.py` ·
`test_stat_race_win_pays_winner_and_reconciles`: winner 10800, loser 9000,
rake 200 — i.e. +$18 / −$10 / $2 — with the conservation invariant asserted).
