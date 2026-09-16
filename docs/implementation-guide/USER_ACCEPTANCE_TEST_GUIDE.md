# Matchbook — Browser Test Guide (for Cursor)

You (Cursor) will **test this app in a browser like a real user**, then **write a
results report**. You will **not** play any real game and you will **not** link the
account to any real game account. Instead, the app has a **self-driving demo
tournament**: it injects real chess stats fetched from the Lichess API (the same
way the app reads game stats), updates them over ~10 minutes to simulate people
playing, and fills the field with bots that also get updating stats. You watch it
run and settle, and verify everything else around it.

All five newer features are now wired into the UI: the **live tournament**, the
**win-streak ladder**, the **Bucketing** page, the **collusion co-entry guard**,
and the admin **fault-based clawback**. §3–§5 tell you where each lives.

At the end, **write `docs/implementation-guide/CURSOR_TEST_RESULTS.md`** (format in
§7).

---

## 1. Start the app

```bash
make dev     # Postgres + API (:8000) + worker + web (:5173)
```

The API needs these flags on (in `.env`):

```
DEMO_LOGIN_ENABLED=true
DEMO_SIMULATE_ENABLED=true
```

- Web UI: **http://localhost:5173**
- API base: **http://localhost:8000/api/v1** (OpenAPI at `/docs`)

If `make dev` can't run, say so in the report and stop — the browser flow needs
the running stack.

---

## 2. Sign in — ANY account works, NO real game link needed

The simulation now works for **any signed-in user**, not just the shared demo
account. Sign in whichever way is available:

- **Real signup** (`/signin` → email/password or Google) — the "real user" path.
  Onboard (username + state + 18+). You start with a gem balance and **no game
  links** — that's fine, the tournament creates a synthetic sim link for you.
- **Demo sign-in** (`/demosignin`) — the shared demo account, pre-linked.

**Do NOT link any real game account.** The chess stats come from the Lichess
**API** (a public account), injected for you — you never play. To reach the admin
console (for the clawback test in §4.4) call **`POST /api/v1/demo/make_admin`**
once with your token (test build only).

**Expect:** you're in the app with a gem balance and a profile showing linked
games. Report the balance and that no real linking was needed.

For any API calls, grab the demo token:

```bash
TOKEN=$(curl -s -XPOST http://localhost:8000/api/v1/demo/login | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
```

---

## 3. ⭐ The self-driving tournament (the main event)

This creates a **~10-minute chess tournament**, enters the demo user + **5
competitive bots**, and injects stats fetched from the real **Lichess API** that
**keep changing** over the window. It **settles itself**, splitting the prize
**60 / 25 / 15**.

### 3.1 Start it — from the UI

1. Go to the **Tournament** tab (`/tournament`).
2. You'll see a **"Demo · self-driving tournament"** panel with a **"Start live
   tournament"** button. Click it.
   - (Equivalent API: `POST /api/v1/demo/live_tournament`.)

### 3.2 Watch it

1. The tournament appears with a **standings board**, your row highlighted, a
   **window countdown**, the entry, the **60/25/15** split, and rake.
2. **Standings should change over time** as games are injected (win counts climb,
   ranks move). To avoid waiting 10 minutes, click **"Advance now"** in the same
   panel a few times (API: `POST /api/v1/demo/live_tournament/tick`) and watch the
   board move.
3. At the window close it **settles**: final ranks, top-3 paid **60/25/15** of
   (pot − rake), your wallet changes if you placed. To settle **now** instead of
   waiting 10 minutes, call `POST /api/v1/demo/force_settle` with
   `{"contest_id":"<tournament_id>"}` (works for any signed-in user in this build).

### 3.3 Verify (report each)

- [ ] The **"Start live tournament"** button exists on the Tournament tab.
- [ ] After starting, a tournament with **6 players** (you + 5 bots), a **60/25/15**
      split, and a countdown appears — with **distinct opening scores** (not all the
      same), your row highlighted.
- [ ] **Standings move** when you click "Advance now" — scores **climb** and ranks
      **reorder** (each advance returns `{"advanced":1}`, not `0`). Scores are a
      running total, so they keep rising and separating the field.
- [ ] It **settles** paying **three different players** 60/25/15 — 1st > 2nd > 3rd,
      distinct amounts, everyone else 0.
- [ ] **Money is conserved:** all payouts + rake == the pot (entry × players).
- [ ] Nothing stuck: no tournament stays "in play" past its window.

If anything is wrong, describe **what actually happened** (scores, ranks, payouts).

---

## 4. The five wired features

### 4.1 Win-streak ladder + 1v1 (Play tab)
- [ ] On **/play**, joining a market now **forms a match against a practice bot**
      (in this sim build) — status goes to `matched`/PENDING. (Previously it sat in
      "Searching" forever.)
- [ ] `POST /api/v1/demo/simulate_result` now works for **any signed-in user** (no
      admin needed) — it injects a result for your own account.
- [ ] After you **win** a 1v1, a **🔥 streak badge** appears on /play and grows
      with each win; a **loss** resets it. (`GET /api/v1/play/streaks` reads it.)
      The streak shifts *who you're matched with*, never what you wager.

### 4.2 Bucketing page (Play modes → Bucketing)
- [ ] There's a **Bucketing** entry in the Play mode switcher → `/bucketing`.
- [ ] With the `bucketing_enabled` flag **off** (default), the page shows a clear
      **"Bucketing isn't enabled yet"** state — not an error, not a crash.
- [ ] (Optional) In **/admin → Flags**, flip `bucketing_enabled` on, reload
      `/bucketing`: it now shows placed markets (or a "play a qualifying match"
      empty state) with a **Wager** action. Flip it back off after.

### 4.3 Collusion co-entry guard (backend, observable on entry)
- [ ] The web app sends a stable **`X-Device-Id`** header (check the Network tab on
      any API call — the request has an `X-Device-Id`).
- [ ] Two accounts on the **same device** can't co-enter the same contest: the
      second tournament entry returns **409 `co_entry_blocked`**. (Hard to do with
      one demo account in a browser — verify via API if you can create a second
      user, or just confirm the header is sent and note the guard is server-side.)

### 4.4 Fault-based clawback (Admin → Disputes)
First reach admin: call **`POST /api/v1/demo/make_admin`** once with your token
(test build only), then reload — `/admin/*` is now accessible.
- [ ] In **/admin → Disputes** there's a **"Bucketing dispute — fault-based
      clawback"** panel with dispute-id + fault-user-id inputs and **Clawback** /
      **Refund** buttons.
- [ ] It calls the bucketing admin resolve endpoint. It needs `bucketing_enabled`
      on and a real bucketing dispute id to fully exercise; at minimum confirm the
      panel renders and the buttons are wired (a bad id returns a clear error, not
      a crash). Report the state you can reach.

### 4.5 Live tournament — covered in §3.

---

## 5. The rest of the app (browser)

For each, ✅ / ⚠️ / ❌ + actual behavior.

### 5.1 Wallet (`/wallet`)
- [ ] Shows available + escrow gems; a demo deposit adds a ledger row; entering a
      contest moves gems to escrow; a void/refund returns them exactly.

### 5.2 1v1 head-to-head (`/play`)
- [ ] Markets list with stake preset + derived multiplier (no house line).
- [ ] Enter → stake escrowed → matched (a practice bot fills the seat).
- [ ] Settle (inject via `POST /api/v1/demo/simulate_result`) → higher stat wins
      pot − rake; a missing result **voids + refunds**.

### 5.3 Solo pools (`/pools`)
- [ ] Markets with difficulty tiers; enter → bots fill → settle (`POST
      /api/v1/demo/force_settle`) → clearers split, or all refunded if nobody
      clears.

### 5.4 Activity / Social / Notifications
- [ ] Activity shows in-flight + recent contests live; Social has friends /
      challenge / chat / inbox; Notifications list match-found / settled / payout.

### 5.5 Disputes + Admin
- [ ] File a dispute from a settled contest.
- [ ] /admin (admin role): Contests, Disputes (incl. the clawback panel), Flags,
      Reconciliation (money invariant + heartbeat healthy), Risk. If you can't
      reach admin, note it.

---

## 6. Cross-cutting invariants (spot-check)

- [ ] **`sum(payouts) + rake == pot`** on every settled contest.
- [ ] **Void + refund** whenever data is missing/late — never a guess.
- [ ] The same host match never counts or pays twice.

---

## 7. Write the results report

Create **`docs/implementation-guide/CURSOR_TEST_RESULTS.md`** with:

1. **Environment** — did `make dev` run? which flags on? setup issues.
2. **Per feature (use the §3/§4/§5 checklists):**
   - ✅ **PASSED** — **how you tested it** (exact clicks / API calls) and what you
     observed that proved it works.
   - ❌ **FAILED** — **how you tested it**, **what actually happened** (error,
     wrong number, missing element, HTTP status, console error), and **how the
     feature behaves right now** (its current, wrong behavior).
   - ⚠️ **PARTIAL** — works with a caveat; describe it.
3. **The tournament (§3) gets its own section** — did it form, did standings update
   as stats were injected, did it settle 60/25/15, money conserved? Include the
   standings you saw and the final payouts.
4. **Summary** — counts of passed / failed / partial, and the top 3 things to fix.

Be specific and factual, so a developer can reproduce any failure from your
description alone.

---

## Appendix — key API calls (demo token in `$TOKEN`)

| Purpose | Call |
|---|---|
| Demo login | `POST /api/v1/demo/login` → `{access_token}` |
| **Start live tournament** | `POST /api/v1/demo/live_tournament` |
| **Advance it now** | `POST /api/v1/demo/live_tournament/tick` |
| Read your win streaks | `GET /api/v1/play/streaks` |
| Become admin (test build) | `POST /api/v1/demo/make_admin` |
| Bucketing markets | `GET /api/v1/bucketing/markets` |
| Bucketing clawback (admin) | `POST /api/v1/bucketing/admin/disputes/{id}/resolve` (`resolution:"clawback"`, `fault_player_ids:[...]`) |
| Inject a 1v1/pool result | `POST /api/v1/demo/simulate_result` |
| Settle a pool/tournament now | `POST /api/v1/demo/force_settle` |
| Reset the demo account | `POST /api/v1/demo/reset` |
| Wallet / ledger | `GET /api/v1/wallet`, `GET /api/v1/wallet/ledger` |
| Tournaments | `GET /api/v1/tournaments`, `GET /api/v1/tournaments/{id}` |

All calls need `-H "Authorization: Bearer $TOKEN"`.
