# End-to-end tests (Playwright)

| Spec             | Covers                                                          | Needs Lichess handles |
| ---------------- | --------------------------------------------------------------- | --------------------- |
| `chat.spec.ts`   | friends → DM → unread badge → reply                             | no                    |
| `chat.spec.ts`   | head-to-head invite from chat → accept → PENDING match          | yes                   |
| `h2h.spec.ts`    | queue blitz at $10 → paired → both confirm → game link          | yes                   |
| `invite.spec.ts` | invite link → preview → accept → both confirm → game link       | yes                   |
| `pools.spec.ts`  | skipped: needs four similar-rated linked accounts and real wins | n/a                   |

Settlement is not driven end to end: it needs the game played to a
result on Lichess. The money math is covered by the API suite
(`apps/api/tests/test_settlement_worker.py`).

Every spec **skips** unless `E2E_AUTH=1`, so none silently passes. The suite is
not in the unit-test CI job; it needs the whole stack and real browsers.

## Auth seam and fixtures

- **API**: with `E2E_AUTH_ENABLED=true` (and `env != prod`),
  `POST /api/v1/dev/e2e/token {auth_id}` mints a short-lived HS256 JWT signed
  with `SUPABASE_JWT_SECRET`, verified by the same path as a real token.
- **web**: built with `VITE_E2E_AUTH=true`, the app reads the token from the
  `mm.e2e.access_token` localStorage key (`src/lib/e2eAuth.ts`).
- **`auth.ts`**: `signInAs(browser, authId)` mints a token and opens a page.
- **`fixtures.ts`**: builds players through the public API (`PATCH /me`,
  `POST /links`, `/friends`, `/challenges`). Steps are idempotent, so the
  linked players reuse stable `auth_id`s across runs.

## Run

```bash
E2E_AUTH_ENABLED=true make dev        # api mints tokens; web built with VITE_E2E_AUTH=true
E2E_AUTH=1 E2E_LICHESS_A=<handle> E2E_LICHESS_B=<handle> make e2e
```

`E2E_LICHESS_A` / `E2E_LICHESS_B` are two real Lichess accounts (linking
verifies them live). A handle binds to one Money Match account for good, so keep
`E2E_AUTH_ID_A` / `E2E_AUTH_ID_B` (defaults `e2e_linked_a` / `e2e_linked_b`)
the same across runs. Pick accounts within ~800 rating points so they pair.

Other overrides: `E2E_USERNAME_A` / `E2E_USERNAME_B`, `E2E_API_BASE_URL`
(default `http://localhost:8000`), `E2E_BASE_URL` (default
`http://localhost:5173`).
