# PUBG completion — settlement, rate limits, mode fairness — design

**Date:** 2026-08-12
**Status:** Approved (brainstorming), pending implementation plan
**Author:** brainstorming session (Shreyansh + Claude)

## Summary

The `pubg.steam` integration is structurally complete (host client, adapter,
registry, markets, pools/tournaments, tests) but only partially functional. Four
defects and a set of lower-severity notes are addressed here:

1. **Stat duels are permanently unplayable** — the adapter's match fan-out cap
   (8) sits below the provisional threshold (10), so a PUBG metric model's `n`
   can never reach 10 and every Kills / Damage / Headshot% duel is rejected as
   `metric_provisional`.
2. **Settlement swallows host outages** — the poll path catches `HostError`
   (which includes `HostUnavailable`), so an outage or 429 looks like "no
   qualifying game" and consumes the settlement window instead of extending it,
   risking a wrong CANCEL or a wrong one-sided forfeit.
3. **Rate-limit budget is blown** — up to ~18 requests per grade / ~9 per link
   against PUBG's ~10 req/min, and a 429 is mis-read as "no game."
4. **No game-mode filtering** — custom / arcade / event matches settle money, and
   the `filters` argument is ignored; team-win attribution is a residual concern.

Plus lower-severity notes: a dead history-floor constant, a stale test docstring,
a missing feature-flag migration seed, and a case-sensitivity hint on linking.

The fixes are game-local: the adapter, the PUBG host client, a new error type,
one linking seam change gated to "deferred" adapters, one worker sweep, and one
migration. Matchmaking, escrow, the settlement worker's money path, and the other
adapters are untouched except for the generic deferred-bootstrap seam.

## Locked decisions

1. **Match-mode policy: official modes, no custom.** Settle only normal + ranked
   solo/duo/squad (fpp & tpp); exclude custom games, arcade, war/zombie, event,
   and training. Team wins count as wins; cross-mode stat comparison (e.g. squad
   kills vs solo kills) is an **accepted residual**, documented not gated.
2. **Rate-limit reconciliation: raise cap + throttle + background bootstrap.**
   Raise the per-poll match fan-out, add a client-side rate limiter to the PUBG
   host client, and move the link-time metric-model bootstrap to the worker so
   linking stays fast and never 429s.

## Confirmed decisions

- **Decision A — bucket sizing / fan-out.** `pubg_rate_limit_per_min = 9`
  (config, tunable), worker bootstrap batch = **1 account per cycle**, per-poll
  match fan-out cap = **15**. 15 recent matches minus filtered-out custom/event
  matches still clears `n ≥ 10` for an active account; the limiter + early-exit
  keep settlement cost bounded.
- **Decision B — durable "needs bootstrap" signal.** Add a nullable
  `models_bootstrapped_at` timestamp column to `linked_accounts` rather than a
  schema-free "no metric rows ⇒ needs bootstrap" heuristic. The heuristic would
  re-poll a genuinely zero-history account forever; the column records the
  attempt.
- **Decision C — cross-process rate limiting.** Ship a **process-local** token
  bucket now and document the caveat (API and worker are separate processes, each
  with its own bucket). PUBG traffic is worker-dominated, so a conservative
  per-process budget keeps the combined rate under PUBG's ~10/min. A Redis-backed
  cross-process limiter is deferred as future work.

## Architecture context (why the design fits)

- All PUBG host calls funnel through `services/hosts/pubg.py`, which uses the
  shared `services/hosts/_client.py::request_json` (retries, typed errors,
  latency logging). The limiter and 429 mapping live at these two layers.
- Grading (`services/grading.py`) is game-agnostic. Its watchdog already turns a
  propagated `HostUnavailable` into `PENDING(host_error)`, and the settlement
  worker (`workers/settlement_worker.py::_resolve_match`) already extends the
  window on `host_error`. The Issue-2 fix is simply to *let the outage
  propagate* out of the PUBG poll path so this existing machinery engages.
- Worker-side metric bootstrapping already exists: `_refresh_after_settle`
  (post-settlement) and `nightly.py` (once/24h) both call
  `metric_models_service.bootstrap`. What is missing is a **fast** trigger for a
  freshly-linked account that has no settled match yet — that is the new sweep.
- `bind()` currently bootstraps **in the same transaction** as the link ("a link
  either lands fully set up or not at all"). Backgrounding must therefore be
  surgical: gated to adapters that declare `defer_bootstrap`, leaving chess /
  CS2 / Dota atomic exactly as today.

## Cross-cutting building blocks

### A. Rate-limit error taxonomy
- `services/hosts/errors.py`: add `HostRateLimited(HostUnavailable)`.
- `services/hosts/_client.py`: map HTTP `429` to `HostRateLimited` (today it is a
  generic non-retryable `HostError`). As a `HostUnavailable` subclass, every
  upstream `except HostUnavailable` (grading watchdog) treats it as a transient
  outage → window extension, never a wrong settle. Narrow the tenacity retry
  predicate so `HostRateLimited` is **not** retried with immediate backoff (it is
  a budget problem, not a flap).

### B. PUBG client-side rate limiter
- `services/hosts/pubg.py`: a module-level async token bucket (≈9 tokens/min from
  `Settings.pubg_rate_limit_per_min`, capacity ≈ the same). Every PUBG request
  acquires a token before calling `request_json`. Process-local (Decision C).
- `config.py`: add `pubg_rate_limit_per_min: int = 9`.

### C. Deferred-bootstrap seam
- `adapters/base.py`: add `defer_bootstrap: bool = False` to `GameAdapter`.
  `PubgAdapter` sets `True`.
- `models/linked_account.py` + migration: add nullable `models_bootstrapped_at`
  (`TIMESTAMPTZ NULL`).
- `services/linking_service.py`:
  - `bind()` — if `adapter.defer_bootstrap`: skip the inline bootstrap, leave the
    column `NULL`. Else: bootstrap inline **and** stamp `now` (unchanged atomic
    contract for cheap adapters).
  - `refresh()` — for deferred adapters, set the column back to `NULL` (worker
    re-bootstraps) instead of bootstrapping inline; unchanged otherwise.
- `workers/settlement_worker.py`: new `_bootstrap_pending_models` sweep in
  `run_cycle` **after** the money-critical work — claim a small batch (**1/cycle**)
  of active accounts with `models_bootstrapped_at IS NULL`, bootstrap (throttled
  by the limiter), stamp `now`. Non-deferred adapters never produce `NULL` rows,
  so they are never touched. A fresh PUBG link becomes fully playable ~1–2 min
  after linking.

## Per-issue design

### Issue 1 — stat duels permanently blocked (CRITICAL)
Raise the PUBG per-poll match cap to **15** (named config constant, e.g.
`PUBG_MATCH_FANOUT`). Combined with the deferred worker bootstrap (block C), a
linked PUBG account reaches `n ≥ 10` and its Kills / Damage / Headshot% duels
become queueable.
- Files: `adapters/pubg.py`, `constants.py`/`config.py`.
- Tests: a PUBG account with `n ≥ 10` is not rejected as `metric_provisional`; a
  genuinely low-history account still is.

### Issue 2 — settlement swallows host outages (HIGH)
Make the settlement path let outages propagate:
- `get_player_by_id`: catch only `HostNotFound → None`; let
  `HostUnavailable`/`HostRateLimited` propagate.
- `get_match`: skip only on `HostNotFound` (a single 404/expired match) and JSON
  errors; let `HostUnavailable`/`HostRateLimited` propagate (an unreadable match
  that might be the qualifying one must extend the window, not silently grade a
  later match).
- `get_lifetime`: **stays fail-soft** (`None` on any error) — soft profile /
  bracketing signal, never settlement. Documented.
- `get_player_by_name` (link path): unchanged — already propagates outages
  (tested).
- Files: `services/hosts/pubg.py`.
- Tests: PUBG host 503/429 during poll ⇒ `GradeOutcome.host_error is True`
  (window extended), not CANCEL; a single seat's match 404 ⇒ "no game yet", not a
  crash. `live_activity_service._window_games` still catches `HostError` →
  "unavailable" cell (unchanged, since `HostUnavailable` is a `HostError`).

### Issue 3 — rate-limit budget blown; 429 mis-read (HIGH)
Builds on A, B, and:
- **Early-exit in `poll_eligible_games`:** iterate the match-id list (PUBG returns
  it newest-first) and **stop** at the first match older than `since_ms`. For
  settlement (`since_ms = matched_at`, recent) this fetches only the 1–3 matches
  after `matched_at`; for bootstrap (`since_ms = 0`) it fetches up to the cap.
  Skip (do not stop) on a `None` normalization (e.g. a filtered custom match).
  The 1h match cache makes repeat settlement cycles ~free.
- **Bootstrap batched 1/cycle** (block C) so a bootstrap burst can't starve the
  budget.
- Files: `services/hosts/pubg.py`, `adapters/pubg.py`, `config.py`.
- Tests: limiter token-bucket timing; poll early-exit stops fetching past
  `since_ms`; newest-first ordering dependency documented.

### Issue 4 — no mode filtering; team-win attribution (MEDIUM)
- Add an **official-mode allowlist** (config): solo/duo/squad × fpp/tpp gameModes
  and their normal/ranked variants.
- In `_normalize`, return `None` (skip) unless `gameMode ∈ allowlist` **and**
  `isCustomMatch` is false **and** `matchType ∈ {official, competitive}`. Gates
  both settlement and bootstrap to official matches.
- Record the match `gameMode` in the stored stat-line detail for auditability.
- `filters.rated_only` stays intentionally unused for PUBG (no rated/casual axis;
  the mode allowlist is the eligibility gate) — documented in a comment so
  "filters ignored" becomes a deliberate, explained choice.
- **Residual (accepted, Decision 1):** squad/duo `winPlace == 1` still credits one
  player, and a stat duel can compare a squad game vs a solo game. Documented in
  the adapter docstring, not gated.
- Files: `adapters/pubg.py`, `constants.py`.
- Tests: official modes accepted; custom (`isCustomMatch`), event/arcade/war
  (`matchType`/`gameMode`) rejected; existing fixtures updated to include
  realistic `matchType` / `isCustomMatch`.

## Lower-severity notes

- **Profile `kd` (revised):** `kills / losses` where `losses = rounds − wins` is
  the conventional PUBG K/D (kills per death-game). The initial review overstated
  this. **No behavior change** — add a clarifying comment on the formula only.
- **Migration seeds `game:pubg.steam`:** the initial migration hardcodes only
  chess/cs2/dota2. Add an idempotent migration seeding the PUBG flag so the admin
  toggle has a row and it matches the "seed it in a migration" convention.
  Behavior unchanged (absent still defaults enabled).
- **Stale test docstring:** `tests/test_pubg_adapter.py` says "adapter is dormant
  (not in the registry yet)" — it is registered. Update the docstring.
- **Link case-sensitivity:** PUBG `filter[playerNames]` is exact/case-sensitive
  and offers no case-insensitive lookup. Improve the "player not found" message
  to hint at exact spelling/case.
- **Match-list ordering / >cap-in-window:** documented known limitation; the new
  early-exit reduces exposure. 14-day retention → an expired match 404s →
  `HostNotFound` → skipped; fine for the 24h window. Documented.

## Dead code

`metric_models_service.meets_history_floor` (and its constant
`GAME_HISTORY_FLOOR`) is defined but never called. Out of scope to remove here;
noted so it is not mistaken for an active gate. The real gate is
`MetricModel.n < METRIC_PROVISIONAL_MIN_N` in matchmaking.

## Testing & verification

- New/updated tests per issue above (each written test-first).
- Confirm `routers/demo.py` seeds PUBG metric models with `n ≥ 10` so **demo**
  stat duels stay non-provisional; add a demo assertion.
- Full `pytest` green — the settlement-invariant suites are the spec and must not
  regress. `ruff` / `prettier` per the repo pre-commit.

## Implementation order (each with a failing test first)

1. Error taxonomy + `_client.py` 429 mapping (A).
2. PUBG host client error propagation (Issue 2).
3. Rate limiter (B) + `config.py`.
4. Adapter: mode allowlist, raised fan-out, early-exit (Issues 1/3/4).
5. Deferred-bootstrap seam + `models_bootstrapped_at` migration + worker sweep (C).
6. Matchmaking + demo verification.
7. Lower-severity notes (migration seed, docstrings, link message, `kd` comment).

## Out of scope

- Mode-matched matchmaking ("mode fixed per contract") — the accepted residual
  makes it unnecessary for now.
- Redis-backed cross-process rate limiting (Decision C).
- Incremental `MetricModel.n` accumulation from settled matches (the raised cap +
  nightly / post-settle re-bootstrap suffice).
- Removing the dead `meets_history_floor` / `GAME_HISTORY_FLOOR`.
