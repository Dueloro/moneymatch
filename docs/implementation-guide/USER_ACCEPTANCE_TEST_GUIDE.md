# Matchbook — User Acceptance Test Guide (for an AI tester)

This describes **how the app should behave from a user's point of view**, feature
by feature, so an automated agent (Cursor) can drive each one and report
**WORKING / PARTIAL / NOT WORKING** — and, when something is off, **describe how it
actually behaves today**.

Read the two setup sections first — especially **§0.3**, which tells you which
features are live in the running app versus which are built-and-tested but **not
yet wired into the UI** (so you verify those via the test suite, not by clicking).
Reporting a not-yet-wired feature as "broken in the app" would be a false negative.

---

## 0. Setup

### 0.1 Run the app

```bash
# from repo root
make dev        # starts Postgres (Docker) + API on :8000 + web on :5173
```

- Web UI: **http://localhost:5173**
- API: **http://localhost:8000** (OpenAPI at `/docs`)
- If `make dev` can't run (no Docker), you can still verify the built-but-unwired
  features via the API test suite — see §0.4 and Part B.

Ensure **`DEMO_LOGIN_ENABLED=1`** is set for the API (it enables a Supabase-free
sign-in). Real Google/email auth also works but needs Supabase configured.

### 0.2 Sign in (demo)

The fastest way to reach every feature without real game accounts:

1. Open the web app → **"Demo sign-in"** (or `POST /api/v1/demo/login`).
2. This provisions one shared **demo user**, already **linked to all four games**
   with seeded stats and a **gem balance**, and seeded sample history/friends.

**Expected:** you land on the app authenticated, with a wallet balance, linked
games on your profile, and joinable contest cards. No onboarding wall.

### 0.3 What's LIVE vs. BUILT-BUT-NOT-WIRED (read this)

- **Part A — Live in the running app.** The full existing product: auth, linking,
  wallet, 1v1 head-to-head, solo pools, tournaments, activity, social, disputes,
  admin, notifications, leaderboard. **Test these through the UI/API.**
- **Part B — Built + unit-tested, but NOT yet connected to the running app.**
  Newer work that will **not appear in the UI yet**: the *bucketing* markets/wagers
  (feature-flagged **off**), the **win-streak matchmaking ladder**, the
  **best-of-N tournament scoring (60/25/15)**, the **collusion co-entry guard**,
  and the **fault-based clawback**. **Verify these by running their tests**, not by
  clicking. For each, Part B says what it should do, the exact test command, and
  what the live app does *instead* today.

If you see a Part B feature missing from the UI, that is **expected**, not a bug.

### 0.4 Reporting format

For every checklist item below, report one of:

- ✅ **WORKING** — behaves as described.
- ⚠️ **PARTIAL** — mostly works; note exactly what deviates.
- ❌ **NOT WORKING** — and then **describe the actual behavior** (error, wrong
  number, missing screen, HTTP status, console error), so it can be fixed.

Group your report by the section numbers here (e.g. "§A3 Wallet: 4/5 working…").

---

# PART A — Features live in the running app

## A1. Authentication & onboarding

- [ ] **Demo sign-in** provisions/logs in the shared demo user and lands you in
      the app with a balance and linked games.
- [ ] **Real sign-in** (Google / email) works when Supabase is configured
      (skip if not configured — note that).
- [ ] A signed-in user's identity persists on refresh (token stored; `GET /me`
      returns the profile).
- [ ] **`GET /api/v1/me`** returns username, residence state, status, 18+ flag.
- [ ] **`PATCH /me`** can update the mutable profile fields.
- [ ] **Self-exclude** (`POST /me/self-exclude`) marks the account excluded and
      blocks further play (responsible-gaming).
- [ ] A **geo-blocked state** (one of the excluded 14) prevents wagering — the app
      should refuse play for those residents, not crash.

## A2. Linking game accounts

Games: **Chess (Lichess), CS2 (Steam), Dota 2 (OpenDota), PUBG (Steam).**

- [ ] **Profile → Games** lists the four games with link/unlink controls.
- [ ] **Link a game** (`POST /links`, or the demo `POST /demo/relink` to swap the
      placeholder handle for a real one) verifies the account exists and shows the
      linked handle + a skill/rank badge.
- [ ] **Link verification is honest:** a nonexistent handle is rejected with a
      clear message; Dota requires public match data exposed; CS2 needs a valid
      Steam account.
- [ ] **One account per game per person:** you can't link two accounts to the same
      game, and the same external account can't be linked by two users.
- [ ] **`GET /links/{game}/profile`** shows the fetched profile (rating, games
      played, win rate).
- [ ] **Unlink** (`DELETE /links/{game}`) removes it (soft-unbind) and the game's
      contest cards disappear.

## A3. Wallet (gems)

- [ ] **Wallet page** shows **available** and **escrow (held)** balances.
- [ ] **`POST /wallet/demo-deposit`** credits gems; balance rises; a **ledger
      entry** appears.
- [ ] **`POST /wallet/demo-withdrawal`** debits gems (subject to a velocity cap —
      too many withdrawals in the window should be refused, not silently allowed).
- [ ] **`GET /wallet/ledger`** shows an **append-only** history: deposits,
      escrow holds/releases, payouts, refunds, rake.
- [ ] **Escrow is real:** joining a contest moves gems available→escrow; you can't
      spend escrowed gems; a void returns them exactly.
- [ ] **Money is conserved:** at no point do total gems increase or vanish outside
      a deposit/withdrawal (spot-check by summing before/after a settled contest).

## A4. Profile & skill

- [ ] **Profile** shows each linked game with its **skill/rating** and **bucket
      band** (matchmaking tier) where available.
- [ ] Stats reflect the linked account's real history (or the demo's seeded
      history).
- [ ] A brand-new/low-history account reads as **provisional / low-confidence**
      and is limited accordingly (see stake caps in A5).

## A5. Play — 1v1 head-to-head (the core loop)

This is the peer-to-peer duel: two players stake gems, each plays a real
matchmade game, higher result wins **pot − rake**; missing/abandoned → **void +
refund**.

- [ ] **`GET /play/markets`** lists the markets you can play per linked game
      (e.g. CS2 kills / K-D / headshot%, chess win, Dota KDA/GPM, PUBG damage/kills)
      with a stake preset ($5/$10/$25 equivalents in gems) and a derived
      multiplier (≈ ×1.8 at 10% rake) — **never a house-set line**.
- [ ] **Enter a queue** (`POST /play/queue`) holds your stake in escrow and puts
      you in matchmaking.
- [ ] **Queue status** (`GET /play/queue/status`) shows waiting → matched.
- [ ] **Fair pairing:** you're matched with a **similar-skill** opponent (forecast
      near 50/50); two far-apart players are **not** matched at base.
- [ ] **Match confirm flow:** a paired match requires both confirms
      (`POST /play/matches/{id}/confirm`); a decline/timeout refunds cleanly.
- [ ] **Settlement:** after both results are read (use `POST /demo/simulate_result`
      to inject a finished match without playing), the higher stat **wins pot −
      rake**; the loser's stake is consumed; **rake is booked**.
- [ ] **`GET /play/matches/{id}/grading`** shows the exact numbers that decided it
      (each player's stat, who won, the payout math) — reconstructable, not a black
      box.
- [ ] **Void + refund** on missing/abandoned data: if a result can't be read, both
      are refunded exactly and **no rake** is taken — never a guessed result.
- [ ] **Stake cap for new accounts:** a fresh/low-confidence account is limited to
      a small stake; the cap grows as confidence grows (anti-smurf money bound).
- [ ] **Chess is the clean 1v1:** for chess the two can be brokered into the *same*
      game and graded on that game id (no separate-lobby luck).

## A6. Solo Pools

A pool is queue-matched: you pick a metric + difficulty + entry, the matcher forms
a fair room, and you're graded on your next qualifying match.

- [ ] **`GET /pools/markets`** lists pool metrics + difficulty tiers (easy/medium/
      hard) with a disclosed clear rate — **difficulty, not odds**.
- [ ] **Enter** (`POST /pools/queue`) holds entry in escrow **only at room
      formation** (no escrow while merely waiting).
- [ ] **Room forms** with similar-skill peers; **`GET /pools`** shows your in-flight
      rooms + queue state ("Open Pools").
- [ ] **Settlement** (force it with `POST /demo/force_settle`): those who clear
      their personal bar split the pot; **nobody clears → full refund, no rake**.
- [ ] **A pool that can't fill** refunds rather than mismatching.
- [ ] **`GET /pools/{id}`** shows members, each personal bar, live result, payout.

## A7. Tournaments

An async tournament over a window; enter, play your own games, ranked at close,
prizes split.

- [ ] **`GET /tournaments/markets`** lists tournament markets (game + scored stat).
- [ ] **Enter** (`POST /tournaments/queue`) holds the entry fee in escrow; a field
      forms under a fairness cap.
- [ ] **`GET /tournaments` / `/{id}`** show standings, your rank, window timer,
      entry, split, rake — **plainly, up front**.
- [ ] **Settlement** (`POST /demo/force_settle`): ranked by score; **top places
      split (pot − rake)**; **underfill → void + refund all** (never a topped-up
      prize).
- [ ] **Ties break deterministically** (never random).
- [ ] **Note the scoring model:** the *live* tournament engine scores the
      **first-N** qualifying games in the window and splits **50/30/20**. The
      plan's **best-of-N (MAX) with 60/25/15** is Part B (not wired yet) — see B3.
      Report what the live app actually does.

## A8. Activity & live view

- [ ] **Activity page** (`GET /activity`) shows your in-flight and recent contests
      (1v1s, pools, tournaments) with live status.
- [ ] A live contest updates (polled/streamed) without a host call on every
      request; a chess board or pool result refreshes while in play.
- [ ] **Server-sent events** (`GET /events/stream`) push updates (new match,
      settlement) — the UI reacts without a manual refresh.

## A9. Social — friends, challenges, chat

- [ ] **Friends** (`GET/POST /friends`): send/accept/decline/block/remove; caps
      enforced (max friends, max pending).
- [ ] **Direct challenge** (`POST /challenges`, or an invite link `/i/{token}`):
      challenge a friend to a specific contest; accept/decline flows work.
- [ ] **Invite link** opens a joinable card for the exact contest; expired links
      are refused.
- [ ] **Chat** (`/chat/conversations…`): DM a friend, send/read messages, respond
      to a challenge card in-thread; the **Inbox** shows threads with unread counts.
- [ ] **Anti-collusion friend cap:** past a per-pair contest cap, a challenge
      becomes a zero-rake friendly rather than another rake-bearing contest.

## A10. Notifications

- [ ] **`GET /notifications`** lists events (match found, settled, payout, dispute
      update); **`POST /notifications/read`** clears them.
- [ ] **Web push** (`/notifications/push/*`): subscribe with the public VAPID key;
      a settlement/match event delivers a push (best-effort).

## A11. Leaderboard

- [ ] **`GET /leaderboard`** ranks real users by ROI over a rolling window; you
      qualify only after a minimum number of settled rake-bearing contests.

## A12. Disputes (user-facing)

- [ ] From a settled contest, **file a dispute** (`POST /play/matches/{id}/dispute`
      or `POST /disputes`) with a reason.
- [ ] **`GET /disputes/{ref_type}/{ref_id}`** shows the dispute status.
- [ ] One dispute per (contest, user); a second is refused.
- [ ] Opening a dispute is visible to admins (A13) and can hold the affected
      payout.

## A13. Admin console

(Requires an **admin** account — role `admin`. Note if you can't reach it.)

- [ ] **Users** (`/admin/users`): search users, see status/KYC, take audited
      actions.
- [ ] **Contests** (`/admin/contests`): inspect any match/pool/tournament — the
      games each participant played, the stat, timestamps, verifying source,
      standings, settlement math, flags. The "check what happened" view.
- [ ] **Disputes** (`/admin/disputes`): review open disputes; resolve
      (no-change / refund) with a note; the action is **audited**.
- [ ] **Flags** (`/admin/flags`): view/flip feature flags (e.g. `queue_paused`,
      `settlement_paused`, `bucketing_enabled`) — a flip takes effect without a
      restart.
- [ ] **Queue** (`/admin/queue`): see the matchmaking/settlement queue depth.
- [ ] **Reconciliation** (`/admin/reconciliation`): the money invariant and worker
      heartbeat show healthy; a stale worker reddens.
- [ ] **Risk** (`/admin/risk`): the risk-flag queue (sandbag/win-streak) — flags
      surface for **review**, never auto-ban.

## A14. Settlement & fairness invariants (spot-check across the above)

- [ ] **`sum(payouts) + rake == pot`** to the gem on every settled contest.
- [ ] **Void + refund** whenever data is missing/late/ambiguous — never a guess.
- [ ] **Idempotent:** the same host match never counts or pays twice; re-running
      settlement doesn't double-pay.
- [ ] **Kill switches:** with `settlement_paused` on, settlement halts and no money
      moves; flipping it off resumes.

---

# PART B — Built + tested, but NOT yet wired into the running app

These will **not** appear in the UI yet. **Verify each by running its tests** (from
`apps/api/`, with a test Postgres — or the pure ones need no DB). For each, report:
does the test pass, and what does the **live app do instead** today?

```bash
# pure logic — runs anywhere, no database:
.venv/Scripts/python.exe -m pytest tests/test_streak_ladder.py tests/test_tournament_scoring.py \
  tests/test_collusion.py tests/test_bucketing_index.py tests/test_bucketing_reference.py \
  tests/test_bucketing_settlement.py tests/test_bucketing_placement.py -m nodb -q

# DB-backed — needs Postgres on :5433:
.venv/Scripts/python.exe -m pytest tests/test_streak_service.py tests/test_bucketing_contest.py \
  tests/test_bucketing_disputes.py tests/test_bucketing_worker.py tests/test_bucketing_api.py -q
```

## B1. Bucketing markets & wagers (feature-flagged OFF)

- **Should:** with `bucketing_enabled` on, `GET /bucketing/markets` shows your
  bucket + a stake cap per market; `POST /bucketing/wagers` holds a stake and
  queues you into a same-bucket room; the room settles against **one bar per
  bucket**; `GET /bucketing/contests/{id}` tracks queued→matched→settled;
  `/explain` reconstructs the grading.
- **Verify:** `test_bucketing_api.py`, `test_bucketing_contest.py`,
  `test_bucketing_worker.py`. Or flip `bucketing_enabled` on in Admin → Flags and
  hit `/api/v1/bucketing/markets`.
- **Live app today:** with the flag **off**, `GET /bucketing/markets` returns
  `{enabled: false, markets: []}` and `POST /bucketing/wagers` returns **404
  `bucketing_not_enabled`**. That is the intended dark-ship state, not a bug.
- **Note:** this bar-based model is a *separate* path from the peer-to-peer plan;
  CS2 and Dota are intentionally gated off until their mode discriminators land
  (chess + PUBG are ready).

## B2. Win-streak matchmaking ladder

- **Should:** win a 1v1 → your **next match targets a slightly higher opponent**;
  win again → higher still (capped); **lose → reset to your own level**; a draw
  holds. It shifts **who you play, never what you wager**. Never matched above
  yourself unless you climbed there by winning (fish protection + anti-smurf).
- **Verify:** `test_streak_ladder.py` (pure) and `test_streak_service.py` (DB —
  `apply_result` climb/reset, `matchmaking_target_for` shifts with streak).
- **Live app today:** **not wired** — the 1v1 settlement path does **not yet call
  `streak_service.apply_result`**, and pairing is **not yet centered on
  `matchmaking_target_for`**. So in the running app your matchmaking target does
  **not** change after a win streak. Expected; report the live behavior as
  "streak has no effect in-app yet (module tested, not connected)."

## B3. Best-of-N-in-window tournament scoring (60/25/15)

- **Should:** your tournament score = your **best game that *finished* inside the
  window** (a game still running at the cutoff **doesn't count**); aggregation is a
  config knob (`max`/`average`/`best_k`); top-3 split **60/25/15 of (pot − rake)**;
  ties break deterministically; **underfill → void + refund**.
- **Verify:** `test_tournament_scoring.py` (incl. cutoff exclusion, the 60/25/15
  reconciliation, and a 2000-tournament money-invariant property).
- **Live app today:** the live tournament engine scores **first-N** games and
  splits **50/30/20** (see A7). The MAX / 60/25/15 model exists as a tested,
  drop-in scorer but the worker is **not pointed at it yet**. Report the live
  split/scoring you actually observe.

## B4. Collusion / same-human co-entry guard

- **Should:** two accounts sharing a **device / IP / payment** signal **cannot
  co-enter** the same contest (blocked + flagged); unknown signals never match, so
  a legit player is never blocked for lacking a fingerprint.
- **Verify:** `test_collusion.py`.
- **Live app today:** **not wired** — device/IP fingerprints aren't captured at
  entry yet, so two colluding accounts are **not** blocked from co-entering in the
  running app. Expected; report as "guard tested, not connected."

## B5. Fault-based clawback (admin)

- **Should:** on confirmed cheating, an admin voids the contest and **refunds the
  honest players from the cheater's balance** (the platform only backstops a
  shortfall if the cheater's wallet is empty); `explain_room` surfaces every
  player's wager/bar/result/full match stats as the evidence.
- **Verify:** `test_bucketing_disputes.py`
  (`test_clawback_refunds_honest_players_from_the_cheaters_pocket`).
- **Live app today:** reachable only via the bucketing admin resolve endpoint
  (`POST /bucketing/admin/disputes/{id}/resolve` with `resolution: "clawback"`),
  which requires `bucketing_enabled` on. The **existing** admin dispute flow (A13)
  does no-change/refund, not fault-based clawback.

---

# PART C — What a healthy end-to-end run looks like (happy-path script)

Do this on the **demo user** to exercise the live loop, then report each step:

1. Demo sign-in → land in app with a gem balance and linked games.
2. Profile shows four linked games with skill/bucket badges.
3. Wallet shows available gems; do a demo-deposit → balance rises, ledger row
   appears.
4. Play → pick a CS2 kills 1v1 at the $5 preset → enter queue → stake moves to
   escrow.
5. Get matched with a similar-skill opponent (or the demo opponent).
6. `POST /demo/simulate_result` to inject both finished games.
7. Contest settles → higher kills wins pot − rake → winner's balance rises,
   loser's stake consumed, rake booked; grading view shows the exact numbers.
8. Sum gems before/after across both players + rake → **conserved to the gem**.
9. Enter a pool → force_settle → clearers split or everyone refunded; balances
   reconcile.
10. Enter a tournament → force_settle → ranked, top split, rake exact; (note the
    live 50/30/20 first-N model, per A7/B3).
11. File a dispute on a settled match → admin sees it → resolve refund → ledger
    returns to pre-payout state; full audit trail intact.
12. Try to over-stake on a fresh account → capped. Try a geo-blocked state →
    refused. Self-exclude → play blocked.

**A healthy system:** every step above works, money is always conserved, anything
unverifiable voids+refunds, and the admin log can reconstruct any contest. Report
any step that deviates with the actual behavior (status code, wrong number,
missing screen).

---

## Appendix — quick endpoint map (for driving via API)

| Area | Key endpoints |
|---|---|
| Auth/me | `POST /demo/login`, `GET/PATCH /me`, `POST /me/self-exclude` |
| Links | `GET/POST /links`, `GET /links/{game}/profile`, `DELETE /links/{game}`, `POST /demo/relink` |
| Wallet | `GET /wallet`, `GET /wallet/ledger`, `POST /wallet/demo-deposit`, `POST /wallet/demo-withdrawal` |
| 1v1 | `GET /play/markets`, `POST /play/queue`, `GET /play/queue/status`, `GET /play/matches/{id}`, `/grading`, `/confirm`, `/decline`, `/dispute` |
| Pools | `GET /pools/markets`, `POST /pools/queue`, `GET /pools`, `GET /pools/{id}` |
| Tournaments | `GET /tournaments/markets`, `POST /tournaments/queue`, `GET /tournaments`, `GET /tournaments/{id}` |
| Demo drivers | `POST /demo/simulate_result`, `POST /demo/force_settle`, `POST /demo/reset` |
| Social | `GET/POST /friends`, `POST /challenges`, `/chat/conversations…` |
| Disputes | `POST /disputes`, `GET /disputes/{ref_type}/{ref_id}` |
| Notifications | `GET /notifications`, `POST /notifications/read` |
| Bucketing (flag) | `GET /bucketing/markets`, `POST /bucketing/wagers`, `GET /bucketing/contests/{id}[/explain]`, `POST /bucketing/disputes`, `POST /bucketing/admin/disputes/{id}/resolve` |
| Admin | `/admin/*` (users, contests, disputes, flags, queue, reconciliation, risk) |
| Health | `GET /health` |

All API routes are under **`/api/v1`** (e.g. `POST /api/v1/demo/login`).
