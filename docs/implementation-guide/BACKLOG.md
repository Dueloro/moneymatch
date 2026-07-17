# Backlog (post-MVP / discovered during build)

Items discovered mid-phase that are out of that phase's scope land here with a
one-line rationale. Seeded with known post-MVP work:

- **OAuth account binding** (Lichess OAuth, FaceIt OAuth2, Steam OpenID) —
  replaces username-claim; prerequisite for anything beyond internal beta
  (integrity audit #5, #6). Targeted Lichess challenges bound to both accounts.
- **Spectate/tracker panels** — port `poc-reference/api/_lib/spectate.py` /
  `tracker.py` + PoC hooks for a live match detail view in Activity.
- **Chess accuracy + Dota solo pools** — needs server-side analysis fetching /
  richer telemetry; engine already game-agnostic.
- **Single-elim bracket tournaments** — real scheduling machinery.
- **Email + push notifications** — `notifications.channel_sent` is ready.
- **Mobile layout pass** — the PDF is desktop-only.
- **Marketing/landing page + waitlist** — gtm-prelaunch.md §2.
- **Host cheat-flag ingestion + clawback** — gems-phase integrity item.
- **Smurf floors** (min account age / rated games / non-provisional rating)
  before public launch.
- **SSE for live surfaces** — replace polling where it hurts.

From the [production launch plan](../proposals/production-launch-plan-v3.md)
(adopted in spirit, deferred past MVP):

- **Payment-processor application timing** — start the processor application /
  underwriting conversation (Stripe restricted-business or a gaming PSP:
  Nuvei/Paysafe/Aeropay/Trustly) **as soon as the public entity + domain
  exist**; approval clocks run in months and require the counsel memo. The
  `PaymentProvider` seam (Phase 7) is the code-side hedge if Stripe declines.
- **Electron overlay rewire** — the launch plan §9 has a full plan (read-only
  device token via `safeStorage`, `GET /overlay/active?game=`, contest-shaped
  card, electron-builder distribution). Only after MVP, and only against the
  new API.
- **Directional value-flow monitoring** between account pairs (collusion/AML)
  — pairs with the Phase-5 pair caps; needed before real money.
- **Chargeback runbook + withdrawal holds** (48–72 h on fresh deposits) —
  real-money items; the ledger `receivable` account concept lands with them.
- **Z-scored tournament scoring** (`(score − μi)/σi` — performance relative to
  your own baseline) — the config escape hatch if raw-value ranking shows the
  top of the μ spread winning too often. Launch on raw value with a tight
  dispersion cap; decide with data.
- **Same-lobby CS2 friend duels** — friends who can join one FaceIt lobby get
  the cleaner same-match objective (no cross-lobby variance) as a fast-follow.

Discovered during Phase 2 (identity & linking):

- **Bind by stable host id, not handle** — MVP stores `host_account_id` as the
  casefolded username/nickname (FaceIt nickname, Lichess username, Dota Steam32
  id). FaceIt nicknames and Lichess usernames are mutable, so a rename breaks
  the binding + settlement poll key. Store the immutable host id (FaceIt
  `player_id`, Lichess canonical id) — lands naturally with OAuth binding.
- **Nightly metric-model refresh job** — Phase 2 refreshes `metric_models` at
  link time and on the `/links/{game}/profile` refresh; the settlement-time
  refresh is Phase 3 and the *nightly* recompute needs the worker (Phase 3+).
  Until then, models only move when a user links/refreshes.
- **Raw-payload back-reference from derived records** — `raw_payloads` retains
  link/profile evidence now; the FK from grading records (matches/entries →
  `raw_payload_id`) lands with those tables in Phase 3/4. *(Done in Phase 3:
  `matches.raw_payload_id` FK + the worker persists grading evidence and links it.)*

Discovered during Phase 3 (head-to-head flow):

- **Browser e2e test-auth seam** — the two-context Playwright spec
  (`apps/web/e2e/h2h.spec.ts`) is written but can't run in CI because auth is
  Supabase-JWT and each context needs a real session. Add a local sign-in bypass
  that mints a session for a seeded user (dev/e2e only) so the flow runs headless
  without a live Supabase project. Until then the exact settlement math is proven
  by `test_settlement_worker.py` (winner +$18 / loser −$10 / rake $2, invariant
  asserted). Rationale: unblocks automated end-to-end coverage of exit criterion #1.
- **Settlement-time metric-model refresh** — Phase 2 backlog noted the *nightly*
  recompute needs the worker; the *per-settlement* refresh (recompute the two
  players' `metric_models` after a match settles) is likewise deferred. Fairness
  is unaffected: in-flight matches use frozen baselines, and models still refresh
  on link / profile-refresh. Rationale: avoids a host round-trip per settlement
  until the nightly job lands; pair the two.
- **Raw pre-normalization payload retention at settlement** — grading persists a
  normalized evidence record (the win/stat inputs + decision) to `raw_payloads`
  and back-refs it from the match. Retaining the *raw* host JSON from the
  settlement poll (as linking already does for profiles) is a stronger audit
  artifact. Rationale: full grading replay from untouched host bytes.
- **Chess grading needs `matched_at`-anchored brokered game only** — `win_h2h`
  settles the stored `host_game_id`; if a Lichess open challenge is never taken,
  it CANCELs at the window with a refund. A friendlier "re-broker on expiry"
  (offer a fresh link before canceling) is a nicety. Rationale: reduce dead
  challenges without changing the money-safe default.

Discovered during Phase 4 (pools & tournaments):

- **Extend the sandbagging block to H2H stat duels** — the detector currently
  gates pool/tournament enqueue (where personal bars live). Tanking a baseline
  also helps a stat *duel* (lower μ → paired vs a weaker forecast). Deferred to
  avoid adding a host call + fixture-stubbing churn to the Phase-3 matchmaking
  path; wire `sandbagging_service.assert_not_sandbagging` into
  `matchmaking._assert_eligible` for `stat_race` markets. Rationale: same attack,
  one call site.
- **Cache the sandbagging evaluation** — `assert_not_sandbagging` polls the host
  adapter on *every* pool/tournament enqueue. Cache the result (or fold detection
  into the nightly metric refresh) and keep only the cheap `risk_flags` check on
  the hot path. Rationale: enqueue latency + host quota.
- **Exact fair-room subset search** — `pool_engine._try_form_room` is greedy
  (nearest bars + composition check); a fair subset can exist that greedy misses
  in a mixed queue. Rationale: marginally higher fill rate once queues are deep;
  irrelevant at MVP volume.
- **Admin sandbagging-review queue** — `risk_flags` rows persist now; the review
  UI + clear/resolve action lands with the Phase-6 admin surface. Rationale: v1
  blocks + records; a human still needs to clear a false positive.
- **Pool/tournament e2e test-auth seam** — same gap as the H2H e2e: the
  Playwright specs need a local sign-in bypass minting sessions for seeded, linked
  users to run in CI. The exact settlement math is proven executably by
  `test_pool_engine.py` / `test_tournament_engine.py` / `test_worker_contests.py`.
- **Nightly metric-model refresh job** (deepened from Phase 2/3) — a stale μ/σ
  now skews personal bars and dispersion fields, not just pairings. The worker
  exists; add the nightly recompute. Rationale: bars must track real form.
