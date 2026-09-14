# Matchbook — Browser Test Guide (for Cursor)

You (Cursor) are going to **test this app in a browser like a real user**, then
**write a results report**. You will **not** play any real game and you will
**not** link the account to any real game account. Instead, the app has a
**self-driving demo tournament**: it injects real chess stats from the Lichess API
(the same way the app fetches game stats), updates them over ~10 minutes to
simulate people playing, and fills the field with bots that also get updating
stats. You just watch it run and settle, and verify everything else around it.

At the end, **write `docs/implementation-guide/CURSOR_TEST_RESULTS.md`** in the
format described in §6.

---

## 1. Start the app

```bash
make dev     # Postgres + API (:8000) + worker + web (:5173)
```

The API must have these env flags **on** (set in `.env`):

```
DEMO_LOGIN_ENABLED=true
DEMO_SIMULATE_ENABLED=true
```

- Web UI: **http://localhost:5173**
- API base: **http://localhost:8000/api/v1** (OpenAPI at `/docs`)

If `make dev` can't run (no Docker), say so in the report and stop — the browser
flow needs the running stack.

---

## 2. Sign in — demo account, NO real game link

1. Open **http://localhost:5173** → click **Demo sign-in** (or POST
   `/api/v1/demo/login`, which returns `{ "access_token": "..." }`).
2. **Do NOT go through "link a game account."** The demo account already has
   placeholder game links and a gem balance. You will never enter a real
   Lichess/Steam handle. The chess stats used later come from the Lichess **API**
   (a public account), injected for you — you are never playing.

**Expect:** you're in the app, authenticated, with a gem balance and a profile
showing linked games. Report the balance and that no real linking was needed.

Grab the demo token for the API calls below (from the browser, or):

```bash
TOKEN=$(curl -s -XPOST http://localhost:8000/api/v1/demo/login | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
```

---

## 3. ⭐ The self-driving tournament (the main thing to watch)

This is the centerpiece. It creates a **~10-minute chess tournament**, enters the
demo user plus **5 competitive bots**, and injects stats fetched from the real
**Lichess API** that **keep changing** over the window (simulating everyone
playing). It **settles itself** at the window close, splitting the prize
**60 / 25 / 15**.

### 3.1 Start it

From the browser console (logged in) or a terminal with the token:

```bash
curl -s -XPOST http://localhost:8000/api/v1/demo/live_tournament \
  -H "Authorization: Bearer $TOKEN"
# → { tournament_id, field_size: 6, prize_split: [60,25,15], window_ends_at, ... }
```

### 3.2 Watch it in the browser

1. Go to the **Tournament** tab (`/tournament`). The new tournament should appear
   with a **standings board**, your row highlighted, a **window countdown**, the
   entry, the **60/25/15** split, and the rake.
2. **Standings should change over time** as more games are injected (every ~45s
   the worker injects another finished game per player, so win counts climb). Your
   rank moves; bots' scores move.
3. To avoid waiting the full 10 minutes, **fast-forward** by injecting rounds
   on demand:

```bash
curl -s -XPOST http://localhost:8000/api/v1/demo/live_tournament/tick \
  -H "Authorization: Bearer $TOKEN"     # advances every live tournament one round
```

   Call it a few times and refresh the Tournament tab — standings should visibly
   move each time.
4. When the 10-minute window closes, the worker **settles** it: the board shows
   final ranks, the **top 3 are paid 60/25/15 of (pot − rake)**, and your wallet
   changes if you placed. (You can watch the window elapse, or note that the
   window is short by design.)

### 3.3 What to verify (report each)

- [ ] The tournament appears in the Tournament tab after starting it.
- [ ] It has **6 players** (you + 5 bots), a **60/25/15** split, a countdown.
- [ ] **Standings update** when you tick / over time (win counts climb; ranks
      move) — this is the "stats fetched from Lichess and updating" behavior.
- [ ] It **settles** at the window close: final standings, top-3 paid 60/25/15,
      wallet reflects any winnings.
- [ ] **Money is conserved:** sum of all payouts + rake == the pot (entries ×
      players). Check the wallet/ledger and the standings payouts.
- [ ] Nothing gets stuck: no tournament stays "in play" past its window.

If any of these is wrong, in the report describe **what actually happened** (e.g.
"standings never changed after 3 ticks — bots stayed at 0", or "settled but
payouts summed to less than the pot by N gems").

---

## 4. The rest of the app (test through the browser)

Sign-in is the demo user throughout. For every item report ✅ / ⚠️ / ❌ + actual
behavior.

### 4.1 Wallet (`/wallet`)
- [ ] Shows **available** and **escrow (held)** gems.
- [ ] A demo deposit increases the balance and adds a **ledger** row.
- [ ] Entering any contest moves gems available→escrow; a void/refund returns
      them exactly.

### 4.2 1v1 head-to-head (`/play`) — includes the **win-streak ladder**
- [ ] `/play` lists markets per game with a stake preset and a derived multiplier
      (no house line).
- [ ] Enter a market → your stake is escrowed → you're matched (a practice bot
      fills the other seat for the demo).
- [ ] Settle it (inject a result via `POST /api/v1/demo/simulate_result`, or use
      the confirm flow) → higher stat wins pot − rake; a missing result **voids +
      refunds**.
- [ ] **Win-streak ladder (now wired):** after you **win** a 1v1, your win streak
      increments; a **loss resets** it. This shifts **who you'd be matched with**
      (aims a bit higher each win), never what you wager. It's a subtle
      matchmaking effect — verify at least that winning a duel doesn't error and,
      if a streak/rank is surfaced anywhere in the UI, that it climbs on wins and
      resets on a loss. (If the streak isn't shown in the UI, note that; the
      backend hook is wired and unit-tested.)

### 4.3 Solo pools (`/pools`)
- [ ] `/pools/markets` lists metrics + difficulty tiers with a disclosed clear
      rate.
- [ ] Enter a pool → bots fill the room → settle (via `POST
      /api/v1/demo/force_settle`) → clearers split, or everyone refunded if nobody
      clears.

### 4.4 Activity / Social / Notifications
- [ ] **Activity** shows your in-flight + recent contests, live.
- [ ] **Social**: friends, a direct challenge / invite link, chat + inbox.
- [ ] **Notifications** list match-found / settled / payout events.

### 4.5 Disputes + Admin
- [ ] From a settled contest, **file a dispute** with a reason.
- [ ] If you can reach **/admin** (admin role): Contests (see what happened),
      Disputes (resolve refund — audited), Flags (flip a feature flag),
      Reconciliation (money invariant + worker heartbeat healthy), Risk (flag
      queue). If you cannot reach admin, note that.

---

## 5. Features that are backend-wired but **not in the UI yet**

Don't file these as "broken in the browser" — they have **no dedicated screen
yet**. Note their state; verify via API/flag if you want.

- **Bucketing wagers** — a parallel bar-based market system, behind the
  `bucketing_enabled` flag (**off**). With the flag off, `GET
  /api/v1/bucketing/markets` returns `{enabled:false, markets:[]}` and
  `POST /api/v1/bucketing/wagers` returns **404**. That's the intended dark state.
  There is no Bucketing page in the web app. Report "present via API behind a
  flag, no UI".
- **Collusion co-entry guard** — the logic exists and is unit-tested, but device/
  IP fingerprints aren't captured at entry yet, so two colluding accounts are not
  blocked in the running app. Report "tested module, not wired to entry".
- **Fault-based clawback** — reachable only via the bucketing admin endpoint
  (`POST /api/v1/bucketing/admin/disputes/{id}/resolve` with
  `resolution:"clawback"`), which needs `bucketing_enabled` on. The normal admin
  dispute flow does refund/no-change, not fault clawback. Report accordingly.
- **Best-of-N tournament scoring** — the *demo live tournament* in §3 already uses
  a 60/25/15 split and updating stats; the standalone "best-of-N (max in window)"
  scorer is unit-tested and used by the demo path. The regular queued tournaments
  still score first-N with a 50/30/20 split — report whichever you observe.

---

## 6. Write the results report

Create **`docs/implementation-guide/CURSOR_TEST_RESULTS.md`** with:

1. **Environment** — did `make dev` run? which flags were on? any setup issues.
2. **Per feature (use the §3 and §4 checklists), one of:**
   - ✅ **PASSED** — and **how you tested it** (the exact clicks / API calls, what
     you observed that proved it works).
   - ❌ **FAILED** — **how you tested it**, **what actually happened** (the error,
     wrong number, missing screen, HTTP status, console error), and **how the
     feature behaves right now** (its current, wrong behavior).
   - ⚠️ **PARTIAL** — works with a caveat; describe it.
3. **The tournament (§3) gets its own section** — did it form, did standings
   update as stats were injected, did it settle 60/25/15, was money conserved? Put
   the standings you saw and the final payouts.
4. **The §5 "not in UI yet" features** — just confirm their current state; don't
   mark them failed.
5. **Summary** — count of passed / failed / partial, and the top 3 things to fix.

Be specific and factual. For anything that failed, the goal is that a developer
can reproduce it from your description alone.

---

## Appendix — key API calls (demo token in `$TOKEN`)

| Purpose | Call |
|---|---|
| Demo login | `POST /api/v1/demo/login` → `{access_token}` |
| **Start live tournament** | `POST /api/v1/demo/live_tournament` |
| **Advance it now** | `POST /api/v1/demo/live_tournament/tick` |
| Inject a 1v1/pool result | `POST /api/v1/demo/simulate_result` |
| Settle a pool/tournament now | `POST /api/v1/demo/force_settle` |
| Reset the demo account | `POST /api/v1/demo/reset` |
| Wallet / ledger | `GET /api/v1/wallet`, `GET /api/v1/wallet/ledger` |
| Tournaments | `GET /api/v1/tournaments`, `GET /api/v1/tournaments/{id}` |
| 1v1 markets / queue | `GET /api/v1/play/markets`, `POST /api/v1/play/queue` |
| Pools | `GET /api/v1/pools/markets`, `POST /api/v1/pools/queue` |

All calls need `-H "Authorization: Bearer $TOKEN"`.
