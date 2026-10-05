# Money Match — Target Spec (for code review)

## Instructions for Cursor

Read this spec, then read the codebase. Write a new document, `GAP_REPORT.md`, with four sections:
1. **Missing** — in this spec, not in the code.
2. **Needs changing** — in the code, but different from this spec (quote file + function).
3. **Must be removed** — anything in the "Not allowed" list that exists in the code.
4. **Needs improving** — works, but is fragile, untested, or unsafe (e.g. no idempotency, floats for money, no tests).

For each item give: file(s), what's wrong, a suggested fix, and priority (P0 = legal/money risk, P1 = core feature, P2 = polish). Order the report by the build order at the bottom. Don't change code yet — report only.

---

## Not allowed (remove if present)

- **The bar / solo pool.** No contest where the platform sets a number (bar, target, line, threshold, "beat X") a player must beat. No per-bucket bar, personal bar, or clear-probability logic. Only contest types allowed: `ONE_V_ONE`, `TOURNAMENT`.
- **The house taking a side.** We never win or lose based on outcomes. Revenue = flat rake only.
- **Guaranteed prizes.** Prize = entries minus rake. If a contest underfills, void and refund — never top up.
- **Self-reported or screenshot results.** Results come only from the game's own API, fetched by our server.
- **Floats for money.** Integer units only (gems). Rates in basis points.
- **Editing or deleting money or audit history.** Fixes are new, compensating records.
- **Wagering on an account without proof of ownership.** PUBG: stats only, no wagering (no ownership proof exists).

Open solo pools that already exist: void and fully refund (no rake), keep settled ones as read-only history.

---

## What must exist

### 1. Per-game stats storage
- `game_accounts`: one external account → one player, ever (`UNIQUE(game, external_id)`). Ownership proven by Lichess OAuth, Steam OpenID (CS2/Dota), or chess.com profile code.
- `matches` (one per host match, host timestamps, host status `completed | player_abandoned | host_cancelled`, full raw JSON) → `player_matches` (one per player per match, `eligible` + reason) → **one stats table per game** (`stats_cs2`, `stats_chess`, `stats_dota2`, `stats_pubg`) with that game's own columns.
- Ingestion is idempotent (`ON CONFLICT DO NOTHING`); ingest all games of linked players, not just contest games; ineligible games are still stored.
- Only ranked/competitive/rated modes are eligible. Chess Blitz and Rapid are separate pools.

### 2. Skill index + buckets (matchmaking only — never a target)
- Per player per pool: mean of best 40% of last 20 eligible games (min 5). Rise fast, fall slow (0.25) once a player has ≥10 games. Floor at 0.85 × 12-month peak. Chess uses the host rating with floor = peak − 150.
- Percentile (0–100) within the pool. 3 buckets by equal-population quantiles; hysteresis 3 points; versioned re-cuts.
- New players with no history start at the median, lowest stakes.
- Skill/bucket is snapshotted onto every contest entry.

### 3. Wallet / ledger (gems)
- Double-entry, append-only; every transaction's entries sum to zero; idempotency key on every operation.
- Accounts: available, held, pending, debt, contest pot, rake, issuance. Only issuance and debt may go negative.
- Joining = hold. Contest starts = capture into pot. Settle = rake + winners' **pending**. Void = full refund, no rake.
- Rake = floor(pot × bps / 10000), taken only at settlement.

### 4. 1v1 with win-streak ladder
- Matchmaking value = `min(100, percentile + 5 × min(streak, 5))`. Win → streak +1; loss → 0; draw/void → unchanged; 24h idle → 0.
- Pair when values are within the search width: 5, +5 every 30s waiting, max 15 (use the smaller of the two players' widths).
- Same stake tier only (10/25/50/100). Stake cap: <5 games → 10, 5–9 → 25.
- **Chess (direct):** both play each other in a Lichess game we create. Draw → full refund.
- **CS2/Dota (parallel):** first game each starts within 45 min after the match goes live is the one that counts. Higher contest stat wins. Tie → full refund. No game → forfeit. Both games in the same host match → void + flag.
- States: queued → proposed (60s accept) → escrowed → live → awaiting result → settled | void.

### 5. Tournaments
- 3 hours, fixed schedule, entry fee, rake, min 6 players, split 60/25/15, bracket = player's bucket (can play up, not down).
- A game counts if: eligible, started after tournament start **and** after entry, **finished by the end time** (host timestamp), and is one of the player's first 3 such games. A game still running at the end doesn't count.
- Score = highest stat of counted games (chess: sum of points). No counted games → can't win.
- Every game gets a stored reason code: `COUNTED, WRONG_MODE, TOO_SHORT, HOST_CANCELLED, STARTED_BEFORE_START, STARTED_BEFORE_ENTRY, ENDED_AFTER_CUTOFF, OVER_GAME_CAP`.
- After the end: wait a grace period (chess 10m, CS2/PUBG 30m, Dota 60m), final poll, lock inputs, settle.
- Ties share the prizes of the places they cover; unfilled places roll up to the winners; house keeps only rake. Under 6 players or no scorers → void and refund.
- Live leaderboard (provisional until settled).

### 6. Anti-exploit
- Smurfs: median start, stake caps, streak ladder, minimum game-account age/games.
- Sandbagging: best-40% index, fall-slow, peak floor, bracket frozen at entry.
- Collusion: same person's accounts can't meet; same pair max 3/day; same-lobby detection.
- Cheating checks: Lichess `tosViolation`, Steam VAC/game bans before payouts mature.
- Detectors create **flags** for human review; high-severity flags freeze pending winnings, never auto-ban.

### 7. Disputes, clawback, admin log
- Winnings stay pending 24h (72h for players with <10 games). Disputes allowed within 24h after settlement; opening one freezes the accused player's pending winnings.
- Admin actions (each requires a written reason): reject, disqualify + re-settle (cheater's entry stays in pot), reverse 1v1, re-settle with late game, void contest (refund all, reverse rake). Settlements are versioned; changes are compensating ledger transactions.
- Append-only, hash-chained `audit_events`; app DB role cannot update/delete it.
- Admin view per tournament: every entrant's games from 1h before start to 1h after end, with stats, times, counted/reason, best game, ledger, flags, disputes.

### 8. Player experience
- Contest cards with the rules in plain words; "your games" panel with counted/reason; notifications; 30-min cutoff warning; practice 1v1s (0 gems); "stay at my level" toggle; pause/void contests if a game's API goes down.

---

## Tests that must exist
Idempotent ingestion; per-game table isolation; sandbag/tank resistance; ledger invariant under fuzz and concurrency; ladder pairing ranges; every 1v1 outcome (win/loss/draw/tie/forfeit/void/same-lobby); tournament cutoff and reason codes; payout examples below; dispute/clawback reversals; audit tamper detection.

**Payout checks** (10 players × 100 gems, 10% rake): normal 540/225/135 · tie for 2nd 540/180/180 · two tied for 3rd 540/225/68/67 · only two scorers 636/264 · 1v1 50 each → winner 90.

## Build order
1. Remove bar · 2. Per-game stats · 3. Skill/buckets · 4. Ledger · 5. 1v1 + ladder · 6. Tournaments · 7. Anti-exploit · 8. Disputes/admin · 9. Player experience
