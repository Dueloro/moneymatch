# Phase 4 — Solo Pools & Tournaments

**Objective:** the two async formats (they absorb thin H2H liquidity — see
`docs/business/business-and-competition.md` §4), ported server-side with
**server-fetched telemetry only**. The PoC's "I cleared it / I missed" buttons
and client-posted scores do **not** survive this port.

Pool/tournament *fairness design* comes from the production launch plan
(§4.5b–c, §4.6 — see [`docs/proposals/production-launch-plan-v3.md`](../proposals/production-launch-plan-v3.md)):
**personalized bars derived from each player's own baseline, rooms formed by
the matchmaking queue, and a server-derived room bar** — no static thresholds,
no user-chosen numbers, no odds surface anywhere.

**Depends on:** Phase 3 (worker, wallet, adapters, metric models, queue).
Parallel with Phase 5.

---

## Scope decisions (settled)

- **Games:** pools and tournaments ship for **CS2 only** at MVP (FaceIt is the
  one adapter with rich server-fetchable telemetry — K/D, ADR, HS%, kills;
  matches the design PDF, which is CS2-themed). Chess pools, when they come,
  use always-available facts (win in ≤N moves, rating gained), **not** engine
  accuracy (Lichess server analysis isn't reliably present per game — launch
  plan §6.1). Dota pools wait for fast-field validation. The engine stays
  game-agnostic — this is config, not code.
- **Pools are queue-matched rooms, not browse-and-join directories.** A player
  picks metric + difficulty (Easy/Medium/Hard) + entry tier and enqueues; the
  matcher forms a room of similar-stat players. The design PDF's "Open pools /
  N playing" surface maps to *your own in-flight rooms* + rooms one confirm
  away from forming.
- **Tournament format:** matchmade single-metric rooms ("play your normal
  matches during the window — your best stat is recorded automatically", PDF
  p.6): ~10 similar-stat players, top 3 split the pot 50/30/20. The PoC's
  simulated single-elim bracket is a demo artifact — cut it.
- **No bots.** PoC bot seeding is gone. Room fill counts display honestly.
  Under-minimum at ladder end → cancel + refund.

## Fairness math (normative — from the launch plan; all constants in config)

**Personal bar (pools).** At enqueue, freeze the player's `baseline_snapshot`
and compute `personal_bar = round_to_increment(μ + k·σ)` with
`k = {easy: 0.5, medium: 1.0, hard: 1.75}`. The three difficulty cards are
quoted **from the player's own numbers** before queueing (a 1.50 K/D player
sees ≈1.60/1.70/1.80); implied clear rates ≈31%/16%/4% (`1 − Φ(k)`) are printed
as *disclosed difficulty*, not odds — the prize is only the entrants' pool
minus rake.

**Room formation.** Group `room_size = 4` (min 3 at ladder end) compatible
tickets `(game, metric, difficulty, entry)`;
`room_bar = round_to_increment(mean(personal_bars))`. Form the room **only if
it stays fair for every member**: each member's implied clear probability vs.
the room bar, `p_i = 1 − Φ((room_bar − μi)/σi)`, must satisfy
`p_target/2 ≤ p_i ≤ min(2·p_target, 0.5)` — a shark can't drag the average
down to trivial-for-them, an outlier can't be dragged up. Plus: personal-bar
spread cap, `can_pair` across every member pair, provisional metrics excluded.
The room card shows the derivation ("Room bar **1.71** — your Medium bar was
1.70"); `room_bar` must reproduce byte-for-byte from the stored snapshots.

**Tournament fields.** Ticket = `(game, metric, entry)`; field of
`field_size = 10` (min 6 at ladder end). Fairness lives in a **μ-dispersion
cap**: `max(μ) − min(μ) ≤ dispersion_cap · σ_pooled` (start ≈1.0). Scoring =
**mean of the metric over the first N = 3 qualifying matches** in the 48 h
window (first-N, not best-of — more games buy zero extra chances; ≥1 match to
rank). Top 3 split `pot − rake` per 50/30/20; ties split combined slices
(remainder cents to earlier enqueue — deterministic, disclosed); zero-match
entrants rank below all who played (forfeit, disclosed); fewer than
`min_ranked = 4` play at all → CANCELED, full refund, zero rake.

## Deliverables

1. Migrations: `solo_pools`, `solo_entries`, `tournaments`, `tournament_entries`
   (per `01-architecture.md` §2).
2. **Pool engine**: settlement math ported from
   `poc-reference/api/_lib/solo_challenge.py` (geo-fence-before-escrow via
   `geo_config`, idempotent entry, settlement invariant: clearers split
   pool − rake; none clear → full refund, zero rake; unverifiable → refund off
   the top; floats → cents, remainder → rake), **plus** the new fairness layer:
   personal-bar derivation at enqueue, room formation with averaged `room_bar`
   and the composition predicate (Fairness math above). Grading = your first
   qualifying match inside the window beats `room_bar`.
3. **Tournament engine**: ranking/prize-split/refund math ported from
   `poc-reference/api/_lib/tournament.py` (leaderboard paths only), with
   matchmade field formation (dispersion cap) and **first-N-average scoring**
   from server-fetched telemetry, tie handling and forfeit ranking per the
   Fairness math section.
4. **Queue extensions** (builds on Phase 3's `queue_tickets`): `product ∈
   pool|tournament` tickets, match-on-write room/field formation, the shared
   widening ladder (band tolerance + spread/dispersion caps relax per stage),
   ladder-end options (start at minimum / keep waiting / cancel + refund),
   ticket TTL via the worker.
5. **Worker extensions**: at window end, for each entrant fetch telemetry
   server-side via the adapter (`poll_eligible_games` within the window →
   `norm_to_telemetry`; persist `raw_payloads`), grade against `room_bar` /
   compute first-N scores, settle, reconcile, notify. During tournament
   windows, refresh live standings on a 10-min cadence (cached, cheap).
6. Endpoints: `/pools*`, `/tournaments*` from `01-architecture.md` §4 (list
   endpoints now return your in-flight rooms + queue state; entering means
   enqueueing). Entries escrow through `wallet_service` with all Phase 1 checks.
7. **Pools screens** (PDF p.4–5): difficulty cards (Easy/Medium/Hard) quoted
   from **your personal bars** with disclosed clear rates; slip shows
   "Clear it and win" + estimated multiplier; after formation, the room card
   shows `room_bar`, your bar, and the delta. Multiplier copy per
   `02-design-system.md` §4 (**estimated**, share-of-pool language —
   legal-critical). "Open pools" = your rooms + forming rooms with honest
   fill counts.
8. **Tournament screen** (PDF p.6): cards with prize pool, 1st/2nd/3rd split,
   fill progress, JOINED chip, and the field's anonymized μ spread ("Field:
   K/D 1.42–1.58" — fairness displayed, not asserted); right-slip live
   standings with you highlighted; settled view with final standings + payouts.
9. Activity feed extended with pool/tournament rows.
10. **Sandbagging detector v1** (launch plan §4.5f): recent-10 mean markedly
    below lifetime mean (z < −1.5) → risk flag, metric wagers blocked pending
    review (admin queue lands in Phase 6). Tanking a baseline is now the
    attack that pays — this detector ships **with** the personal-bar feature,
    not after it.

## Reuse from `poc-reference/`

| What | From | Change |
| --- | --- | --- |
| Pool engine + geo-fence | `api/_lib/solo_challenge.py` | port; drop bot seeding + client telemetry |
| Tournament engine | `api/_lib/tournament.py` | leaderboard paths only; drop bracket sim + `genScore` |
| Invariant test suite | `tests/test_tournament.py` | port fully — it is the settlement spec |
| MetricTarget/MetricKind shapes | `api/_lib/schemas.py` | the rate-metric allowlist; CS2 metrics only at MVP |
| Stat distribution inspection | FaceIt Lab distribution route in `api/index.py` (`/api/dev/faceit/distribution`) | becomes an admin/calibration script for `k`/cap tuning |
| Pool/tournament copy helpers | `frontend/src/utils/soloText.ts`, `tournamentText.ts` | adapt to new design language |

## Tests required

- Ported invariant suite green on cents: every settlement branch
  (`sum(payouts) + rake == sum(entries)`), renormalized splits, refund paths.
- Personal bars: `μ + k·σ` derivation and rounding; provisional metric
  (`n < 10`) cannot enqueue; bars frozen at enqueue (a model refresh mid-queue
  doesn't move the bar).
- Room formation: `room_bar == round(mean(personal_bars))`; the composition
  predicate refuses a shark (their `p_i` breaches the cap) and a hopeless
  outlier; spread cap enforced; `can_pair` across all member pairs; no
  user-supplied bar/number accepted anywhere (crafted-request test).
- Room-bar reproducibility: `room_bar` and every `personal_bar` re-derive
  byte-for-byte from stored `baseline_snapshot`s (audit replay test).
- Tournament fields: dispersion cap refuses a lopsided field; first-N scoring
  averages exactly N earliest qualifying matches (not best-of, not latest);
  tie-split math with remainder cents deterministic; `min_ranked` cancel path.
- Grading: missing telemetry → refund never fail; window-boundary matches
  excluded.
- Geo-fence: excluded-state user blocked at enter (403) **before** any ledger
  write; allowed after `geo_config` change without deploy.
- Sandbagging detector: fixture with tanked recent form gets flagged and
  blocked from metric wagers.
- e2e: enqueue → room forms at `room_size` → fixture telemetry clears →
  payout equals share of pool.

## Exit criteria

- [ ] A CS2 user picks Medium, sees bars quoted from their own baseline,
      enqueues, lands in a formed room whose `room_bar` is the rounded mean of
      members' bars (shown with the delta), plays a (fixture) FaceIt match, is
      graded from server-fetched telemetry, and is paid their pool share —
      zero client input after enqueue.
- [ ] No self-report control exists anywhere in the UI or API, and no API
      surface accepts a user-supplied bar, room bar, or payout number.
- [ ] A tournament field forms under the dispersion cap, completes a window
      with live standings, and pays exactly the 50/30/20 table (tie case
      exercised).
- [ ] Under-filled queues resolve via the ladder-end options; no escrow is
      ever stranded (watchdog test).
