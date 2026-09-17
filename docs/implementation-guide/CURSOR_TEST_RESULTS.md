# Cursor browser UAT results

Tested **2026-09-16** against local `feat/bucket_system` with the demo account. Follows `USER_ACCEPTANCE_TEST_GUIDE.md`. No real game account was linked and no real match was played.

Status key: **PASSED** / **FAILED** / **PARTIAL**.

---

## 1. Environment

| Item | Result |
|---|---|
| `make dev` | **Did not run.** `make` is not installed on this Windows machine. |
| Equivalent stack | **Started and healthy.** Postgres already listening on `:5432`. `alembic upgrade head` (already at head). API `uvicorn` on `:8000`. Settlement worker. Vite on `:5173`. |
| Flags | `.env` has `DEMO_LOGIN_ENABLED=true` and `DEMO_SIMULATE_ENABLED=true`. API logged `api.demo_login_enabled`. `GET /api/v1/health` → `env=local`, `bucketing_enabled=false`, `worker.stale=false`. |
| Web URL | `http://localhost:5173` (Vite bound to **IPv6 `[::1]:5173` only** — `http://127.0.0.1:5173` is connection-refused). |
| API URL | `http://127.0.0.1:8000/api/v1` |

**Cursor IDE browser:** navigating to `http://localhost:5173/signin` and `http://127.0.0.1:5173/signin` both returned `ERR_CONNECTION_REFUSED` (`chrome-error://chromewebdata/`). The embedded browser can load public sites (example.com) but not this machine’s loopback. The rest of the UAT was driven in **local Playwright Chromium** against `http://localhost:5173`, clicking the same controls a user would.

Demo user from `POST /api/v1/demo/login`:

- email `demo@dueloro.com`, username `demo`, **role `user` (not admin)**
- `active_games`: chess, CS2, Dota 2, PUBG
- starting wallet: **$850.00 available, $0.00 escrow** (85000 / 0 cents)

---

## 2. Sign-in (demo, no real game link)

### `/signin` Demo button — PARTIAL

**How:** opened `http://localhost:5173/signin`.

**Observed:** email + password, Continue with Google, Sign up. **No** “Demo sign-in”, “Skip demo”, or “Enter the demo” control. Demo entry is the hidden route `/demosignin`.

### Demo sign-in — PASSED

**How:** opened `/demosignin` (auto `POST /api/v1/demo/login`), clicked **Continue** on the game-select overlay if it appeared.

**Observed:** landed on `/pools` as `demo`. Rail balance **$850.00**. No Steam/Lichess OAuth was used. Profile (`/profile`) shows placeholder game rows (“Link an account when you're ready to play for real”, CS2 “Not connected”) — no real linking was required.

### Wallet on entry — PASSED

**How:** opened `/wallet` after demo login.

**Observed:** **AVAILABLE $845.00** after the live tournament had taken $5 escrow; **$5.00 in play · +$142.00 all time**. (Immediately after login, before the tournament, API wallet was $850.00 / $0 escrow.)

---

## 3. Self-driving tournament (main event)

Tournament id: `0be21ba9-dd7c-40c4-a2df-2982bb7db238`.

### 3.1 “Start live tournament” button — PASSED

**How:** opened `/tournament`.

**Observed:** panel **“Demo · self-driving tournament”** with copy about a ~10-minute chess field, Lichess-injected stats, and 60/25/15. Button **Start live tournament** was present on the first visit; after start it correctly became **Tournament running** (disabled). A later visit with an already-running field therefore showed `Start button count=0` — that is the running state, not a missing control.

### 3.2 Field, split, countdown — PASSED

**How:** clicked **Start live tournament**, waited ~4s, read the Tournament tab and `GET /api/v1/tournaments`.

**Observed:**

- 6 players: `#1 demo (you)`, NovaBot, PixelBot, EchoBot, VegaBot, ZephyrBot
- `prize_split: [60, 25, 15]`, `field_size: 6`, `entry_cents: 500`, `pot_cents: 3000` (Pot **$30.00**)
- `state: LOCKED`, window `16:38:46Z` → `16:48:46Z` (~10 minutes)
- Wallet: **$5.00 in play**, ledger row `demo live tournament entry` **−$5.00**

### 3.2 Standings update / “Advance now” — FAILED

**How:**

1. Clicked **Advance now** twice right after start.
2. `POST /api/v1/demo/live_tournament/tick` immediately → `HTTP 200 {"advanced":0}`.
3. Waited 50s (past `tick_seconds=45`), posted tick again → still `{"advanced":0}`.
4. Reloaded `/tournament` and clicked **Advance now** again.
5. Cross-checked settlement-worker logs.

**What happened:** the LIVE STANDINGS board never moved. It stayed:

```
#1 demo (you)   1.00 · 1 matches
#2 NovaBot      1.00 · 1 matches
#3 PixelBot     1.00 · 1 matches
#4 EchoBot      1.00 · 1 matches
#5 VegaBot      1.00 · 1 matches
#6 ZephyrBot    1.00 · 1 matches
```

**Why (current behavior):**

- `demo_tournament.tick()` only injects when `now >= last_tick_ms + tick_seconds` (45s). The settlement worker already calls that same `tick()` every cycle, so the UI **Advance now** button usually no-ops (`advanced: 0`) — it is not a true fast-forward.
- Worker logs **did** inject extra wins (~every 45s; 6 injected rounds by settle time). `standings_updated_at` stayed `16:38:53Z` (set once at formation). Live standings refresh is gated by `TOURNAMENT_STANDINGS_REFRESH_SECONDS = 10 * 60`, so the board kept showing the first-game cache for the whole 10-minute window.

So: stats were being written; the UI the guide asks you to watch did not change.

### 3.3 Settlement, 60/25/15, money, stuck-in-play

The natural window was 10 minutes. To exercise the **worker** settle path without waiting, `window_ends_at` was set a few seconds in the past. The worker settled at `16:43:37Z` (`tournament.settled ranked=6 refunded=0`).

**Money conserved — PASSED**

| | cents |
|---|---|
| pot (6 × $5) | 3000 |
| rake (1000 bps) | 300 |
| prize | 2700 |
| sum of entry `payout_cents` | 2700 |
| payouts + rake | **3000 = pot** |

**Top-3 60/25/15 — FAILED**

**How:** read `Tournament` + `TournamentEntry` after `SETTLED`; opened `/activity`.

**Observed:** every player had `score=6.0`, `matches=6`, **`rank=1`**, **`payout_cents=450`** ($4.50). Activity line:

> Chess · Total wins tournament · **#1** · **Lost** · **−$0.50** · YOUR SCORE 6 · FIELD 6 · ENTRY $5.00 · PRIZE POOL $27.00

Expected unique 60/25/15 of $27.00 = **$16.20 / $6.75 / $4.05**. Actual: six-way tie, $4.50 each (net −$0.50 vs the $5 entry).

**Why:** each tick injects a **win for every participant**, so `chess_wins` stays identical. The engine then splits tied slices evenly. The 60/25/15 weights are stored on the row but never produce 1st/2nd/3rd places in this demo.

After settle, `/tournament` returned to idle (**Start live tournament** enabled again). Nothing stayed “in play” past the window — **PASSED** for the stuck-in-play check.

Final standings (post-settle, from DB/API — not from the live board, which never showed this):

| Rank | Player | Score | Matches | Payout |
|---|---|---|---|---|
| 1 (tie) | demo (you) | 6 | 6 | $4.50 |
| 1 (tie) | NovaBot | 6 | 6 | $4.50 |
| 1 (tie) | PixelBot | 6 | 6 | $4.50 |
| 1 (tie) | EchoBot | 6 | 6 | $4.50 |
| 1 (tie) | VegaBot | 6 | 6 | $4.50 |
| 1 (tie) | ZephyrBot | 6 | 6 | $4.50 |

Wallet after settle: tournament prize **+$4.50**, escrow released; then a later $10 pool hold.

---

## 4. The five wired features

### 4.1 Win-streak ladder (`/play`) — FAILED

**How:** opened `/play`; `GET /api/v1/play/streaks`; `POST /api/v1/demo/simulate_result` `{game:"chess.lichess", won:true}` with the demo token (the path the guide names).

**Observed:**

- `/play` markets render (Chess Blitz “Win the game”, ENTRY $5/$10/$25, **YOU WIN $18.00**, $2.00 platform fee, **Find match**). That part is fine.
- `GET /play/streaks` → `{"streaks":[]}`. No `data-testid="streak-badge"`.
- `POST /api/v1/demo/simulate_result` → **HTTP 403** `{"code":"forbidden","message":"Admin access required."}`.

The demo account is `role=user`. `simulate_result` is `AdminUser`. There is no way for this UAT account to inject a 1v1 win, so the 🔥 badge and “rung higher per win” matching were **not exercisable**.

### 4.2 Bucketing page — PASSED (optional flag flip PARTIAL)

**How:** Play mode switcher → `/bucketing`. `GET /api/v1/bucketing/markets`. Health flag `bucketing_enabled=false`.

**Observed:**

- **Bucketing** is a Play-mode tab (`/bucketing`).
- Empty state **“Bucketing isn't enabled yet”** plus the flag explanation. Not an error, not a crash.
- API `HTTP 200 {"enabled":false,"markets":[]}`.

Optional admin flag flip: **not done**. Demo user is not admin; `/admin/flags` redirects to `/pools`.

### 4.3 Collusion co-entry guard — PARTIAL

**How:** Playwright request interceptor on every `/api/v1/*` call from the web app. Read `tournaments._guard_co_entry`.

**Observed:**

- Web app **does** send **`X-Device-Id: 5c5016d0-fd3c-454c-9892-71afe490c2cc`** (and `localStorage mm_device_id`). **PASSED** for the header.
- 409 `co_entry_blocked` was **not produced**. `POST /demo/login` is a single shared account. The server guard **skips demo users** (`test_opponents.is_enabled` → return). A second real user on the same device was not created.

### 4.4 Fault-based clawback — FAILED

**How:** navigated to `/admin/disputes`. `POST /api/v1/bucketing/admin/disputes/00000000-0000-0000-0000-000000000000/resolve` `{resolution:"clawback", fault_player_ids:[...]}` with the demo token.

**Observed:**

- `/admin/disputes` **redirected to `/pools`** (`RequireAdmin`: `role !== 'admin'`). The “Bucketing dispute — fault-based clawback” panel **never rendered** in this account.
- API → **HTTP 403** `Admin access required.` (clear error, not a crash).

### 4.5 Live tournament — see §3.

---

## 5. The rest of the app

### 5.1 Wallet (`/wallet`) — PARTIAL

**How:** opened `/wallet`; clicked a `$10.00` pill; later `POST /api/v1/wallet/demo-deposit` `{amount_preset_cents:1000}`; entered tournament + pool.

**Observed:**

- Available + escrow display works (**$845.00**, **$5.00 in play**, then **$859.50** after API deposit, then **$849.50 / $10.00 in play** after the pool).
- First UI click on `$10.00` **did not change the balance**. There are two `$10.00` buttons (Add funds and Cash out); the first click did not create a ledger row.
- API deposit **did** work: `available 84950 → 85950`, ledger **Add funds · just now · +$10.00**. Reloading `/wallet` showed that row.
- Entering the live tournament moved **$5.00** to escrow; joining the easy pool moved **$10.00** to escrow. Void/refund of a missing result was **not reached** (no 1v1 settle, pool window is 24h, `force_settle` is admin-only).

### 5.2 1v1 (`/play`) — PARTIAL / FAILED on match + settle

**How:** opened `/play`; clicked **Find match** (the actual label; not “Join”); `GET /api/v1/play/queue/status`; `POST /demo/simulate_result`.

**Observed:**

- Markets + stake presets + derived payout (no house line) — **PASSED** ($5 → You win $18, $2 fee).
- **Find match** → **Searching… Matching you tightly on skill… Waiting 4s / Cancel search**. After **81s** still `status: "searching", match: null`. **No practice bot filled the seat.** Escrow did not move for the 1v1 (hold happens on match, not on queue).
- Settle via `simulate_result` — **FAILED** HTTP 403 admin-only.
- Missing-result void + refund — **not tested** (never reached a result window).

### 5.3 Solo pools (`/pools`) — PARTIAL

**How:** opened `/pools`; clicked **Join pool** then **Confirm · $10.00**; `GET /api/v1/pools/queue/status`; `POST /api/v1/demo/force_settle`.

**Observed:**

- Difficulty tiers (Easy / Medium / Hard, personal bars, clear %) — **PASSED**.
- Confirm joined a **LOCKED** 4-player chess easy room: demo + **testbot_ada / testbot_bo / testbot_cy**, pot $40.00, **$10.00 in escrow**, rail “Your $10.00 is in escrow, so you can now play your Chess game.” Bots filled. — **PASSED** for enter.
- `force_settle` — **FAILED** HTTP 403 admin-only. Pool window is **24 hours**, so this session could not watch clearers-split vs all-refund.

### 5.4 Activity / Social / Notifications — PASSED

**How:** `/activity`; `/social`; `/social?tab=friends`; `/social?tab=leaderboard`.

**Observed:**

- Activity: live tournament then settled tournament, in-progress pool, older won/lost chess pools, **Contest this result**.
- Social Inbox: Dueloro Support thread, DMs (chocoTaco, kvem_, s1mple_fan), Notifications (“A contest settled”, “Your pool room filled”).
- Friends: friend code **MM-8JFWWM**, Message / Challenge / Remove.
- Leaderboard: **demo (you) · 12 contests · -34.1%**.

### 5.5 Disputes + Admin — PARTIAL

**How:** on `/activity` clicked **Contest this result** on a settled easy pool, typed a reason, submitted. Then visited `/admin/users|contests|disputes|flags|reconciliation|risk`.

**Observed:**

- Dispute file — **PASSED**. The row became **“Contested · under review”**.
- Admin tree — **FAILED** for this account. Every `/admin/*` URL redirected to `/pools`. Contests / Flags / Reconciliation / Risk / clawback panel were not reachable. Demo `role=user`.

---

## 6. Cross-cutting invariants (spot-check)

### `sum(payouts) + rake == pot` — PARTIAL

**How:** DB read of the live tournament after settle, plus the five most recent `SETTLED` solo pools.

**Observed:**

- Live tournament: **2700 + 300 = 3000**. OK.
- 4-player chess pools (e.g. `1c955a07…`, `8c7b10af…`): pot 10000, rake 1000, payouts 9000. OK.
- Historical pool `0d1f5518-430a-4e8e-89cc-33275c4a39fb`: `state=SETTLED`, `pot=5000`, `rake=0`, `prize=0`, **one** entry `MISSED` payout 0, `room_size=4` `min_entrants=3`. **0 + 0 ≠ 5000**. Not created in this session (old row) but it fails the stated invariant.

### Void + refund on missing/late data — not tested

No 1v1 reached `AWAITING_RESULT`, and the new pool cannot be force-settled as demo.

### Same host match never counts/pays twice — not tested

No graded 1v1 this session.

---

## 7. Summary

| | Count |
|---|---|
| PASSED | 18 |
| FAILED | 9 |
| PARTIAL | 8 |

Counts are checklist items in §2–§6 (including sub-bullets that were independently judged).

### Top 3 things to fix

1. **Live tournament UI does not show play.** `Advance now` shares `tick()` with the worker and usually returns `advanced: 0`. Live standings are cached for **10 minutes**, so the board stays at `1.00 · 1 matches` while the worker is injecting games. A tester cannot “watch standings change” as the guide describes.

2. **Self-driving tournament cannot demonstrate 60/25/15.** Every tick writes a **win for every seat**, so all six finish tied at rank 1 and each receive $4.50. Activity even labels the demo user’s #1 finish a **Loss (−$0.50)**. Inject uneven results (or only some players win each tick) if the point of the demo is a 60/25/15 payout.

3. **The UAT demo account cannot finish the guide’s settle paths.** `simulate_result`, `force_settle`, `/admin/*`, and clawback are **admin-only**. The demo user is `role=user`, so 1v1 results, pool force-settle, Flags (`bucketing_enabled`), Reconciliation, and the clawback panel are unreachable. Either make those demo routes callable by the demo token, or document an admin login. Related: **Find match** sat in `searching` for 81s with **no practice bot**; `/signin` no longer has a Demo button (`/demosignin` works).

### Also noted (not in the top 3)

- Cursor’s in-IDE browser cannot load localhost; Vite is IPv6-only (`[::1]:5173`).
- Wallet has two `$10.00` pills; a naive click on the first `$10.00` did not deposit. API `POST /wallet/demo-deposit` works.
- `make` is missing on this Windows host; the stack was started with the Makefile’s equivalent commands.
