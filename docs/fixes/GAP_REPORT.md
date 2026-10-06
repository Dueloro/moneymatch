# Gap Report: code vs `MONEY_MATCH_SPEC_FOR_CURSOR.md`

**Audited:** `feat/future_system`, which is identical to `main` (`031f344`). Report only; no code was changed.

**Priority:** P0 = legal or money risk · P1 = core feature · P2 = polish.
**Step** = the spec's build order (1 Remove bar · 2 Stats · 3 Skill/buckets · 4 Ledger · 5 1v1 · 6 Tournaments · 7 Anti-exploit · 8 Disputes/admin · 9 Player UX).

### Note on `feat/bucket_system` (44 commits ahead of main)
- **Already done there, worth porting:** the Solo Pool backend and UI are deleted (`d27f0b5`, `e9eb469`). It also adds the win-streak ladder (`streak_ladder.py`, `streak_service.py`), stake caps (`stake_limits.py`), a same-human collusion guard (`collusion.py`, `fingerprint_service.py`), best-game tournament scoring with a 60/25/15 split (`tournament_scoring.py`), and a clawback panel.
- **Do not merge as-is:** `services/bucketing/contest.py`, `bucketing/settlement.py`, `reference.bars` and `routers/bucketing.py` still run a **one-bar-per-bucket contest**. That is a platform-set bar, which the spec forbids. Also leave out `demo_tournament.py`, which runs bot fields. Keep only the index and placement code, and only for matchmaking.

---

## 1. Must be removed

| Step | What | File(s) | Fix | P |
|---|---|---|---|---|
| 1 | **Solo pools (the bar).** Personal bar, room bar, clear probability, difficulty tiers | `models/pools.py`, `services/pool_engine.py`, `services/fairness.py` (`personal_bar`, `room_bar`, `clear_prob`, `composition_ok`, …), `routers/pools.py`, `schemas/pools.py`, `constants.py` (`POOL_*`, `POOL_DIFFICULTY_K`, `METRIC_BAR_INCREMENT`, `METRIC_LOWER_IS_BETTER`, `METRIC_FLOOR`, …), `money_math.pool_multiplier_estimate_bps`, `telemetry_fetch.grade_pool`, worker `_process_due_pools` + pool live snapshots, `live_activity_service` pool parts, `dispute_service` "pool" type, `queue_tickets.product='pool'`, `personal_bar` column. Web: `usePools.ts`, `ClearBar.tsx`, pool bits of `WagerCard`/`ActivityCard`. Tests: `test_bar_*`, `test_pool_*` | Delete it all (cherry-pick from bucket branch). Add a migration that **voids and fully refunds every OPEN/LOCKED pool (no rake)** and keeps SETTLED pools as read-only history | P0 |
| 1 | `cs2_prior` exists to quote a pool bar from Steam lifetime stats | `services/cs2_prior.py`, called in `routers/cs2.steam_callback` | Delete. New players start at the median (step 3) | P1 |
| 1 | **Practice bots that always lose.** Platform-created opponents enter paid contests, then are graded as forfeits, so the real player's prize is guaranteed and paid from money the house seeded | `services/test_opponents.py`; call sites `routers/play.py:244`, `routers/pools.py:181`, `routers/tournaments.py:227`; `telemetry_fetch` (`graded_as_failed`) | Delete. Spec practice 1v1s are 0-gem, human vs human | P0 |
| 1 | **Fabricated results.** Injected fake matches and forced settlement | `routers/demo.py` (`/simulate_result`, `/force_settle`), `models/demo_simulation.py`, `adapters/simulated.py`, `services/demo_simulation.py`, wrapper in `adapters/registry.get` | Delete. Results may only come from the host API. If demo code stays for now, fail boot in production when `demo_login_enabled` or `demo_simulate_enabled` is set (`config.py` has no such guard today) | P0 |
| 1 | Demo accounts are graded on casual games | `services/demo_mode.rated_only_for` | Delete along with the demo code | P1 |
| 1 | **PUBG wagering** | `services/markets.py` (PUBG `win_next`/kills/damage/HS%), `constants.POOL_GAMES` / `TOURNAMENT_GAMES` (= all games) | PUBG is stats only. Remove it from markets and tournaments, and block it at enqueue | P0 |
| 1 | **Wagering on unproven accounts.** Lichess links by typed username. Dota links by typed id or persona search. For CS2, `POST /links` with `game=cs2.steam` and any 17-digit number binds **without Steam OpenID** | `adapters/chess_lichess.link_account`, `adapters/dota2_opendota.fetch_profile`, `adapters/cs2_steam.fetch_profile`, `routers/links.create_link`, `services/linking_service.bind` | Lichess: OAuth. CS2 and Dota: Steam OpenID only. `POST /links` must refuse username linking for money games. Mark existing unproven links stats-only until re-verified | P0 |
| 1 | **Player-chosen CS2 results.** A player pastes share codes by hand, so a bad game can simply never be submitted, and the "first game counts" rule breaks | `routers/cs2.submit_share_code`, `services/cs2_submission.py` | Only count matches ingested automatically from the share-code chain (every match). Remove manual paste as a result source | P0 |
| 1 | **House keeps rounding leftovers.** Floor remainders are added to rake, so the house takes more than `floor(pot × bps / 10000)` | `services/money_math.split_pot`, `split_weighted` | Rake = exact floor. Leftover units go to players (top place first; within a tie, the earlier entry). This also fixes the spec example 636/264 (code gives 635/264, rake 101) | P0 |

---

## 2. Missing

| Step | What | File(s) | Fix | P |
|---|---|---|---|---|
| 2 | **Per-game stats storage.** No `matches` / `player_matches` / `stats_cs2` / `stats_chess` / `stats_dota2` / `stats_pubg` tables. Only `cs2_matches` + `raw_payloads` exist, and grading re-fetches history from the host every cycle | new models + migration; `adapters/*`; `services/metric_models_service.py` | Add the tables with `UNIQUE(game, external_id)` on game accounts and on host matches. Store host timestamps, host status and raw JSON | P1 |
| 2 | **Idempotent ingestion job** for all games of linked players (not just contest games), keeping ineligible games with a reason | new worker step | `INSERT … ON CONFLICT DO NOTHING`, one pass per linked account per cycle | P1 |
| 2 | **Game end time and host status.** `NormGame` has only `created_at_ms` | `adapters/base.py` + each adapter | Add `ended_at`, `status` (`completed / player_abandoned / host_cancelled`), `eligible`, `reason` | P1 |
| 2 | chess.com linking (profile-code ownership proof) | new adapter | Add later | P2 |
| 3 | **Skill index.** Best 40% of last 20 eligible games (min 5); rise fast, fall slow (0.25) after ≥10 games; floor at 0.85 × 12-month peak; chess = host rating with floor peak − 150 | today: `metric_models_service.compute_ewma` (EWMA μ/σ) | New index module (bucket branch `bucketing/index.py` is a starting point) | P1 |
| 3 | **Percentile + 3 buckets.** Equal-population quantiles, hysteresis 3, versioned re-cuts | none | Reuse bucket branch `placement.py` / `reference.py` **without bars** | P1 |
| 3 | New players start at the median with the lowest stakes | none | Default the index to the pool median | P1 |
| 3 | Skill/bucket snapshot on every contest entry | `baseline_snapshot` holds μ/σ/rating only | Add percentile, bucket, and cut version to the snapshot | P1 |
| 4 | **Double-entry ledger.** Rows are one-sided per wallet plus a separate `platform_ledger`; there is no transaction id and no "sums to zero" check | `models/wallet.py`, `services/wallet_service.py` | `ledger_transactions` + `ledger_entries(account, amount)`; the DB asserts `SUM = 0` per transaction | P0 |
| 4 | **Idempotency key on every money operation** | `wallet_service.*` | Unique `idempotency_key` per transaction (e.g. `settle:match:<id>:v1`) | P0 |
| 4 | Accounts **pending, debt, contest pot** (issuance = today's `platform:promo`) | `wallet_service.py`, `models/wallet.py` | Add them. Only issuance and debt may go negative | P0 |
| 4 | **Pending winnings.** Hold 24h (72h for players with <10 games), then mature to available | none | Maturation job; payouts credit pending | P0 |
| 4 | Capture into pot when a contest starts | holds stay in wallet escrow until settle | Hold on join → capture to the contest pot account at start | P1 |
| 5 | Win-streak ladder: `min(100, pct + 5·min(streak,5))`; win +1, loss 0, draw/void unchanged, 24h idle → 0 | none on main | Port from bucket branch | P1 |
| 5 | **Same host match = void + flag** (both players in one CS2/Dota match) | `services/grading._grade_coordinated` | If both seats' counted games share a host match id → CANCEL + high-severity flag | P0 |
| 5 | Stake caps: <5 games → 10, 5–9 → 25 | none on main | Port `stake_limits.py` | P1 |
| 5 | 60-second accept step (`proposed`) | `MATCH_CONFIRM_TTL_SECONDS = 24h` | Proposed state with a 60s timeout → back to queue | P1 |
| 6 | **Scheduled 3-hour tournaments** you join (fixed start/end), bracket = your bucket (can play up, not down) | today: queue-formed fields (`tournament_engine._try_form_field`) | New tournament schedule model + join flow | P1 |
| 6 | **Per-game reason codes** stored: `COUNTED, WRONG_MODE, TOO_SHORT, HOST_CANCELLED, STARTED_BEFORE_START, STARTED_BEFORE_ENTRY, ENDED_AFTER_CUTOFF, OVER_GAME_CAP` | none | Store on `player_matches` per contest | P1 |
| 6 | **Grace period → final poll → lock → settle** (chess 10m, CS2/PUBG 30m, Dota 60m) | worker settles right at `window_ends_at` | Add a grace per game before settling | P1 |
| 7 | Minimum game-account age / games before wagering | `account_age_days` is captured but never checked | Gate at enqueue | P1 |
| 7 | Same person, many accounts (device/IP/payment) | `matchmaking.can_pair` checks only same user / same host account | Port `collusion.py` + `fingerprint_service.py` | P1 |
| 7 | **Cheat checks before payouts mature.** Lichess `tosViolation`; Steam VAC / game bans | bans fetched only for the profile label | Check at maturation; create a flag and freeze if hit | P0 |
| 7 | Flag severity; high severity freezes pending winnings | `models/risk.py` has no severity | Add `severity`; freeze hook on pending | P1 |
| 8 | **Dispute window (24h after settle)** and freezing the accused player's pending winnings | `services/dispute_service.file_dispute` (no time check, no freeze) | Add both | P0 |
| 8 | **Admin money actions:** disqualify + re-settle (cheater's entry stays in pot), reverse a settled 1v1, re-settle with a late game, void a tournament (refund all, reverse rake). Every action requires a written reason | only `resettle_match` / `void_match`, both refuse settled matches; no tournament actions | New admin actions that post compensating transactions | P0 |
| 8 | Versioned settlements | none | `settlements(contest, version, …)`; re-settle = new version + compensating txns | P1 |
| 8 | **Hash-chained `audit_events`**; the app DB role cannot UPDATE/DELETE it | `models/admin_audit.py` (has `updated_at`, no trigger, no hash) | New append-only table with `prev_hash`; trigger + `REVOKE` | P0 |
| 8 | Admin tournament view: each entrant's games from 1h before start to 1h after end, with stats, times, counted/reason, best game, ledger, flags, disputes | `admin_contests_service._tournament_detail` shows entries + ledger only | Extend once per-game storage exists | P1 |
| 9 | "Your games" panel with counted/reason; 30-min cutoff warning; practice 1v1s (0 gems); "stay at my level" toggle | none | Build after steps 2 and 6 | P2 |
| 9 | Pause/void contests when a game's API is down | only per-entry refund on outage | Per-game outage flag → pause, then void + refund | P1 |

---

## 3. Needs changing

| Step | What | File + function | Fix | P |
|---|---|---|---|---|
| 2 | Dota counts every match as eligible (`rated=True`) | `adapters/dota2_opendota.poll_eligible_games` | Ranked lobby only | P1 |
| 2 | PUBG "official" modes include normal matches | `constants.PUBG_OFFICIAL_MATCH_TYPES` | Stats only anyway; mark only ranked as eligible | P2 |
| 2 | Chess offers bullet and classical; spec has Blitz and Rapid as separate pools | `chess_lichess._CLOCK_FOR_SPEED`, `markets` `win_h2h` | Limit to blitz / rapid | P2 |
| 4 | Payouts go straight to available | `match_lifecycle.settle`, `tournament_engine.settle_tournament` → `wallet_service.payout` | Pay to pending | P0 |
| 4 | Wallet can't go negative (`ck_wallets_available_nonneg`), so a clawback after withdrawal is impossible | `models/wallet.py` | Shortfall goes to the debt account | P0 |
| 4 | Money is dollars in "cents" (`*_cents`, `$5/$10/$25`, `DEMO` currency) | `models/wallet.py`, `constants.ENTRY_PRESETS_CENTS`, web | Integer gems; tiers 10/25/50/100 | P1 |
| 5 | Pairing uses stat forecast / Elo band | `matchmaking._is_eligible`, `services/pairing.py`, `constants.PAIRING_WIDENING_LADDER`, `CHESS_*_BAND` | Matchmaking value; width 5, +5 per 30s, max 15, use the smaller width | P1 |
| 5 | New players are blocked from stat duels (`n < 10`) | `matchmaking._assert_eligible` (`METRIC_PROVISIONAL_MIN_N`) | Allow from 5 games, with stake caps | P1 |
| 5 | CS2/Dota: the first game in a 24h window counts, plus a 2h forfeit grace | `grading._first_qualifying_game`, `MATCH_SETTLE_WINDOW_SECONDS`, `FORFEIT_GRACE_SECONDS` | First game **started within 45 min** of going live; none → forfeit | P1 |
| 5 | `win_next` market (win your own next match) is not in the spec (spec: higher contest stat wins) | `services/markets.py` | Remove, or confirm it should stay | P2 |
| 5 | Same pair: queue allows 1/day (24h cooldown); challenges allow 3/day, then turn "friendly" | `REPAIR_COOLDOWN_SECONDS`, `PAIR_RAKE_CONTESTS_PER_DAY` | One rule: max 3 paid contests per pair per day | P2 |
| 6 | Split is 50/30/20 | `constants.TOURNAMENT_PRIZE_SPLIT` | 60/25/15 | P1 |
| 6 | Score = mean of first 3; chess = win streak / total wins / fastest win | `fairness.first_n_average`, `services/aggregate_metrics.py`, `TOURNAMENT_METRICS` | Highest stat of counted games; chess = sum of points | P1 |
| 6 | A game counts if it *started* inside a 48h window; entry time and end time are ignored | `telemetry_fetch._window_games`, `TOURNAMENT_WINDOW_SECONDS` | Started after start **and** after entry, finished by end (host time), first 3 only | P1 |
| 6 | Settles with ≥4 participants (`TOURNAMENT_MIN_RANKED`) | `tournament_engine.settle_tournament` | Under 6 players or no scorers → void + refund | P1 |
| 6 | Field fairness uses a μ-dispersion cap | `tournament_engine._field_ok` | Bucket bracket, frozen at entry | P1 |
| 7 | Sandbagging detector auto-blocks wagers | `sandbagging_service.assert_not_sandbagging` / `assert_not_flagged` | Flag for human review; only high severity freezes pending, never auto-block | P2 |
| 8 | Resolving a dispute moves no money | `dispute_service.resolve` | Link a resolution to an admin action (reverse / re-settle) | P1 |
| 8 | Re-settle takes no reason | `routers/admin/contests.resettle_match` | Require a written reason on every admin action | P1 |

---

## 4. Needs improving

| Step | What | File(s) | Fix | P |
|---|---|---|---|---|
| 4 | Settlement "exactly once" relies only on state checks + row locks; there is no ledger-level guard | `match_lifecycle.settle`, `tournament_engine.settle_tournament` | Unique idempotency keys (see Missing) | P0 |
| 4 | Ledger fuzz tests cover only pure math (`nodb`); nothing checks the invariant under concurrent DB writes | `tests/test_money_invariants_property.py` | Add a concurrent join/settle/refund fuzz on Postgres, checking every transaction sums to zero | P1 |
| 4 | `platform_ledger` recomputes `SUM()` on every booking under an advisory lock | `wallet_service._book_platform` | Keep a running balance row | P2 |
| 2 | Grading hits host APIs live every 15s cycle for every open contest (rate limits; results can shift if host history changes) | `grading.py`, `telemetry_fetch.py` | Grade from stored ingested games | P1 |
| 1 | Admin unlink hard-deletes the link row (fails on played accounts, loses history) | `linking_service.unlink` | Soft-unbind only | P2 |
| all | **Tests missing:** idempotent ingestion; per-game table isolation; tank resistance of the new index; ladder pairing ranges; 1v1 same-lobby / forfeit / void; tournament cutoff + every reason code; spec payout examples (540/225/135 · 540/180/180 · 540/225/68/67 · 636/264 · 1v1 → 90); dispute/clawback reversals; audit tamper detection | `apps/api/tests/` | Add them as each step lands | P1 |

---

### Already OK (no action)
- Money is integer units with rake in basis points (`money_math`, `test_no_floats_in_money_path.py`).
- `ledger_entries`, `platform_ledger` and `raw_payloads` are append-only via DB trigger (`db/append_only.py`).
- Each contest is reconciled before commit, and a breach halts settlement (`reconciliation_service`, `_assert_reconciled`).
- Refunds on push/cancel take no rake. Chess draws refund. Equal stats refund.
- `UNIQUE(game, host_account_id)` on linked accounts.
- Tournament ties split combined places, with the leftover to the earlier entry. Unfilled places roll up to the winners (only the remainder handling is wrong, see §1).
- Live tournament standings (`standings_cache`), notifications, geo-fence, and limits all exist.
