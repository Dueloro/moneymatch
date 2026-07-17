# Phase 3 — Head-to-Head Challenge Flow

**Objective:** the core product loop, end-to-end and server-authoritative:
pick a market → stake → match with a **real second user** → play the real game →
the settlement worker verifies and pays. Ships the Play and Activity screens.
This phase is the heart of the MVP.

**Depends on:** Phases 1 + 2. **Unblocks:** Phases 4 + 5.

---

## Deliverables

1. Migrations: `queue_tickets`, `matches`, `match_players`
   (per `01-architecture.md` §2), plus `markets` config (static Python config is
   fine — game → market defs with resolution rules; no DB needed).
2. **Matchmaking service** — the PoC queue skeleton
   (`poc-reference/api/_lib/match_queue.py`) onto Postgres, with pairing
   upgraded to the launch-plan §4.5(d) **duel-forecast model**:
   - Hard compatibility: same `(game, market, speed, entry)`.
   - **Eligibility** (stat duels): model each player's next-match performance
     as an independent normal from their `metric_models` row, giving
     `P(a beats b) = Φ((μa − μb) / √(σa² + σb²))`; pair only if
     `P ∈ [0.5 − w, 0.5 + w]`. Chess `win_h2h` uses the rating band instead
     (Elo already *is* the forecast; keep the PoC band + `win_expectancy`).
   - **Selection** among eligible candidates: lowest composite score
     `0.60·|μa − μb|/σ_pooled + 0.30·rating distance + 0.10·|σa − σb|/σ_pooled`
     (the variance term avoids pairing a steady player with a boom-or-bust one).
   - **Widening ladder** (config, queue-depth aware): `w = 0.05` for 0–30 s
     → `0.10` to 2 min → `0.15` to 5 min; past that, offer keep-waiting /
     cancel-refund. Chess band: 100 → widens 12/s → max 800 (PoC constants).
   - Transactionally: `SELECT … FOR UPDATE SKIP LOCKED` candidates, create
     `match` (PENDING) + `match_players` with **frozen `baseline_snapshot`s**,
     mark tickets matched — match-on-write, no double-match under race (test it).
   - `can_pair` hook: reject self-pair (same user **or** same linked host
     account), same-pair-within-24h, and provisional metrics (`n < 10`). This
     is the anti-collusion seam — keep it one function.
   - Ticket TTL (10 min) → expired by the worker; no escrow while waiting.
   - The matched confirmation card shows the forecast honestly ("Even duel —
     model gives you 52%") — the P2P analog of rake disclosure.
3. **Match lifecycle service** (one transition per function, all transactional):
   - `confirm(match, user)` → escrow via `wallet_service.escrow_hold`. Both
     confirmed → `activate`: chess → create a **Lichess open challenge
     restricted to the two linked usernames** (`users=a,b` — only those two
     accounts can take the seats; store the game id and settle **that game**,
     not "next qualifying"); CS2/Dota → coordinated mode ("play your next
     match") with `matched_at` stamped **server-side**.
   - `cancel/decline` (PENDING) and expiry (`window_ends_at`, 24 h) → refund
     both, no rake.
   - `settle(match, result)` → winner payout + rake row, or push → refund.
     States: `PENDING → ACTIVE → AWAITING_RESULT → SETTLED | PUSHED | CANCELED`.
4. **Settlement worker** (`workers/settlement_worker.py`, separate process):
   the loop from `01-architecture.md` §3.3. For each due ACTIVE match, call the
   adapter's resolve with the match's market:
   - `win_h2h` (chess): the brokered game's result between the two bound
     accounts (PoC adapter logic); draw → PUSH.
   - `win_next` (CS2/Dota): each player's first finished match after
     `matched_at`; win beats loss; both-win/both-lose → PUSH (design copy:
     "Win beats loss · tie = push").
   - Stat races (`kd_ratio`, `adr`, `headshot_pct`, `kda_ratio`, `gpm`): grade
     each player's stat from their first finished match after `matched_at` via
     `norm_to_telemetry`; higher wins; equal → PUSH; store both stat lines in
     `match_players.stat_line` for the Activity UI.
   - **Forfeit rule** (one-sided stat duel): if only one player produced a
     qualifying match, they win — but only after the full window **plus a
     disclosed grace period**; the rule is printed on the slip pre-entry.
   - **Host outage** does not consume the window: extend `window_ends_at` by
     the downtime, hard ceiling 24 h → CANCELED + refund (failure matrix,
     `01-architecture.md` §3.4).
   - Any other unresolvable state at window end → CANCELED + refund.
     Settlement rows record `engine_version` and reference the `raw_payloads`
     used. Post-settle: run `reconciliation_service.check(match)`; on failure
     set `settlement_paused` and alert (fail closed).
5. Endpoints: the `/play/*` set from `01-architecture.md` §4, including
   `GET /play/waiting` (open tickets of others, the design's "Waiting to play"
   list) and `POST /play/waiting/{ticket_id}/match` (take the other side
   directly — same pairing checks).
6. **Play screen** (PDF p.1–2): market rows with derived multiplier, waiting
   list with Match pills, slip panel state machine (pick → presets + "You'd win"
   → Find match → searching (band + cancel) → matched (opponent card + Confirm)
   → active ("Go play" with play_url for chess / instructions for CS2/Dota)).
   Balance header with live "$X in play" escrow figure.
7. **Activity screen** (PDF p.9): unified list from `GET /activity` (H2H now;
   pools/tournaments join in Phase 4) with status dots, stat-race result lines,
   signed amounts. Settled matches get a lightweight settlement toast/modal
   (reuse PoC settlement-modal behavior).
8. Notifications emitted (consumed by Phase 5's Inbox; write rows now):
   `match_found`, `settled`, `refund`.

## Ordering within the phase

Backend first (2 → 3 → 4 with tests at each step), then endpoints, then UI.
The worker must be running in `make dev` from this phase on.

## Reuse from `poc-reference/`

| What | From | Change |
| --- | --- | --- |
| Queue pairing + lifecycle logic | `api/_lib/match_queue.py` | in-memory dicts → tables; floats → cents; keep the pure-function shape |
| Queue tests | `tests/test_matchmaking.py` | port against the DB-backed service |
| Rake config + bracket labels | `api/_lib/skill_rating.py` | keep `rake_for`, `win_expectancy`, `make_bracket` nearly as-is |
| H2H resolution per game | `api/_lib/adapters/*` `resolve_contract` + `api/index.py` settle route | becomes worker + adapter calls; server-owned `matched_at` |
| Lichess challenge brokering | PoC route in `api/index.py` (search "challenge") | port; targeted challenges when OAuth lands post-MVP |
| Telemetry stat grading | `cs2_faceit.py::norm_to_telemetry` | reused for stat races |
| Slip/queue UX logic | `frontend/src/hooks/useMatchmaking.ts`, `useContracts.ts` | poll intervals + state handling patterns only |

## Tests required

- Pairing: compatibility matrix (game/market/speed/entry), forecast-window
  eligibility (a pairing outside `0.5 ± w` cannot be formed, even via a crafted
  direct-match request), ladder widening over time, composite-score selection,
  self/same-host/24h-repeat/provisional rejection, race-safety (two concurrent
  enqueues, one waiting ticket → exactly one match), baseline snapshots frozen
  at escrow (later model refreshes don't alter an in-flight match).
- Lifecycle: full happy path escrow math; decline/expiry refunds; double-confirm
  idempotent; confirm with insufficient balance fails and match stays PENDING.
- Worker (adapter-mocked): each market's win/lose/push/unresolvable branch →
  correct ledger rows; invariant check after every settle; crash between claim
  and settle leaves the row re-claimable (SKIP LOCKED semantics).
- e2e (Playwright, two browser contexts): two users queue at $10 K/D ratio →
  matched → both confirm → mock host fixture resolves → winner +$18.00, loser
  −$10.00, rake $2.00 in platform ledger.

## Exit criteria

- [ ] Two real users on separate machines complete queue → match → confirm →
      (real or fixture-resolved) game → auto-settlement, no manual steps.
- [ ] Tampered clients can't affect money: entry presets only, no amounts or
      timestamps in any request body, settle has no public endpoint at all.
- [ ] Kill switches work: `queue_paused` empties into refunds gracefully;
      `settlement_paused` halts the worker loop.
- [ ] Activity + Play screens match the PDF; footer breadcrumbs correct.
