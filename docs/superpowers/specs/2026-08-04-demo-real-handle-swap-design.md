# Demo real-account handle swap — design

**Date:** 2026-08-04
**Status:** approved

## Problem

The shared demo user (entered via `POST /api/v1/demo/login`) is auto-linked to
every game with a **placeholder** `host_username="demo"` and synthetic profile /
metric fixtures (`routers/demo.py::_ensure_demo_fixture`). No real game data ever
flows, so the demo can't be used to test the real account-linking pipeline
against live host APIs.

We want: inside the demo, swap the placeholder handle for a **real** handle per
game (real Lichess / FACEIT / PUBG / OpenDota account), run the live adapter
verification, and show the real profile snapshot + skill metric.

## Scope (agreed)

- **In:** link a real handle → live adapter verify → real profile snapshot +
  skill metric bootstrapped from real match history.
- **Out:** matchmaking, settlement, grading against live results.
- **UX:** a dedicated demo-only "change handle" panel on the Profile page.
- **Audience:** internal testing on the single shared demo user. No per-tester
  isolation; last write wins (documented, acceptable).

## Key constraints discovered

- `linking_service.bind` rejects a second live link for the same `(user, game)`
  via the partial-unique index `uq_linked_accounts_user_game`
  (`postgresql_where: status <> 'unbound'`). So a swap must free the slot first.
- `linking_service.unlink` **hard-deletes**, but `match_players.linked_account_id`
  is `ondelete=RESTRICT` and the demo has seeded CS2/PUBG matches referencing the
  placeholder links — a hard delete would fail. The right tool is **soft-unbind**
  (`status='unbound'`), which frees the partial-unique slot while keeping the row
  for FK history (see `models/linked_account.py` and `admin_service.force_unbind`).
- `metric_models_service.bootstrap` upserts on `(user_id, game, metric)`, so
  re-binding safely overwrites the seeded fixture models with real values.
- Frontend already exposes `useAuth().isDemo` (`getDemoToken() != null`).

## Design

### Backend

1. **`linking_service.rebind(session, user, game, username)`** — new seam:
   - `existing = get_link(session, user.id, game)`; if present, set
     `existing.status = "unbound"` and flush (soft-unbind, frees the slot).
   - `return await bind(session, user, game, username)` (live verify + fresh
     active row + metric bootstrap). All in the caller's transaction: a bad
     handle raises inside `bind`, the transaction rolls back, and the original
     link is preserved.

2. **`POST /api/v1/demo/relink`** — in the **demo router** (only mounted when
   `DEMO_LOGIN_ENABLED=true`). Body `{ game, username }`.
   - Guard: `user.auth_id == DEMO_AUTH_ID`, else 404 (`not_found`). This leaves
     the real users' `/links` flow and the admin-only unlink untouched.
   - Calls `linking_service.rebind`, commits, returns `LinksResponse` (reusing
     the `/links` response builder so the frontend reuses existing types).
   - Errors bubble up unchanged: bad handle → `host_account_unlinkable` (404),
     host down → 502, unknown/disabled game → existing `LinkError`.

### Frontend

- **`useDemoRelink`** mutation hook (POST `/demo/relink`, invalidate the links
  query) alongside the existing `useCreateLink` / `useRefreshLink`.
- **`DemoHandles`** component: one row per registered game — current handle, a
  real-username input, and Save. On save → verify → the row shows the real
  profile snapshot + skill badge (reusing `skillBadge`) or an inline error.
- Rendered on `ProfilePage` **only when `isDemo`**. The normal `LinkGames` UI is
  unchanged for real users.

### Data flow

`DemoHandles input → POST /demo/relink → rebind (soft-unbind + bind) → live host
API verify → real snapshot + metric models persisted → LinksResponse → panel
renders real profile/skill.`

## Testing

- **API (service):** `rebind` swaps an existing link to a new handle (old row
  `unbound`, new row active with real profile); `rebind` with no existing link
  just binds.
- **API (endpoint):** demo user swaps placeholder→real (respx-mocked host);
  non-demo caller → 404; bad handle rolls back leaving the old link intact.
- **Web:** `DemoHandles` renders only in demo mode; Save calls the hook and
  renders the returned snapshot.

## Caveats

- Lichess + OpenDota need no API key. **FACEIT + PUBG need `FACEIT_API_KEY` /
  `PUBG_API_KEY`**; without them those relinks fail-soft with a host error. A
  config dependency, not a code gap.
- Shared demo user: concurrent testers overwrite each other's handles. Accepted.
