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

Discovered during Phase 5 (social & retention):

- **Invite-link e2e test-auth seam** — `apps/web/e2e/invite.spec.ts` is written
  but (like the H2H/pool specs) can't run in CI: the funnel needs a fresh,
  un-onboarded Supabase session for user B and a seeded/linked session for A. The
  funnel is proven executably by the API tests (`test_challenge_service.py`:
  single-use token, expiry, fresh-signup accept, unlinked-prompt;
  `test_challenges_endpoints.py`: public preview + accept). Pair with the same
  seam the H2H/pool specs need.
- **Pair rake-cap exact-count race** — `challenge_service` recomputes `friendly`
  at *accept* time, but several challenges created under the cap could each accept
  near-simultaneously and momentarily exceed it before the next recompute reads
  the just-committed rows. At MVP volume this is negligible; a hard guarantee
  wants a serialized per-pair counter (or the directional value-flow monitoring
  already backlogged). Rationale: soft anti-collusion control, not a money
  invariant — the ledger is unaffected.
- **Sandbagging on friend stat-duel challenges** — challenges intentionally skip
  the provisional/forecast-fairness gates (friends consent to skill gaps with
  disclosure). A tanked baseline still can't move money unfairly in a *friendly*,
  but a rake-bearing friend challenge on a stat market inherits the same
  unguarded-duel gap noted in Phase 4. Pair with that item's single call site.
- **Friend-code collision retry** — `gen_friend_code()` has a vanishing but
  nonzero collision chance against the unique constraint; provisioning should
  retry on the rare `IntegrityError` (as onboarding does for usernames).
  Rationale: one-in-a-billion today, but a clean signup should never 500.
- **Challenge "Respond" deep-link polish** — the Inbox Respond pill accepts and
  routes to `/play?match=…`; the Play screen doesn't yet auto-open that match
  slip from the query param. Wire the `?match=` param into `PlayPage` so Respond
  lands directly on the confirm card. Rationale: closes the last click of the
  challenge loop; the match is reachable via Activity meanwhile.
- **Email/push for the social fan-out** — `notifications.channel_sent` is ready;
  friend requests, challenges, and settlements are the first events worth an
  out-of-band nudge (return-trigger layer). Pairs with the backlog email/push item.

Discovered during Phase 6 (admin & instrumentation):

- **Soft-unbind with contest history** — `admin_service.force_unbind` hard-deletes
  a `linked_accounts` row and returns a clean 409 when a `match_players` /
  `queue_tickets` FK (RESTRICT) references it, so an account that has *played*
  can't be rebound. A real rebind needs a soft-unbind (nullable/append-only
  binding table or a `status='unbound'` + freed unique slot) that preserves
  history. Lands naturally with OAuth binding. Rationale: MVP covers the common
  case (wrongly-linked fresh account); history rebind is rare and destructive.
- **Admin pool/tournament re-settle & void** — the money-fix actions
  (`resettle` / `void`) are wired for **matches** (the H2H exit-criterion path).
  Pools/tournaments settle on window end via the worker; a stuck one currently
  needs a manual adjustment. Add engine-level admin re-settle/void for
  `solo_pool` / `tournament` refs. Rationale: matches are the representative,
  tested path; the contest detail (money trail + reconciliation) already covers
  all three types.
- **Disputes model for the risk view** — the risk dashboard reports
  `dispute_count = 0` because there is no dispute entity yet. Add a `disputes`
  table (ref + reason + state) and a user-facing "flag this result" path, then
  surface counts + a queue in `/admin/risk`. Rationale: needed before real money;
  self-report is deliberately absent, so disputes must be operator-mediated.
- **Derived risk detectors (streaks / pair-cap)** — the flag queue surfaces the
  persisted sandbagging `risk_flags`; "abnormal win streaks" and "pair-cap
  breaches" are named in the phase doc but not yet computed as flags. Add
  detectors (nightly, alongside the metric refresh) that write `risk_flags` rows
  of new kinds. Rationale: the risk *rates* view already exposes drift; the
  streak/pair signals are additive and want their own detector + migration.
- **Reconciliation sweep is O(all contests)** — `check_contests` iterates every
  match/pool/tournament each call. Fine at MVP volume; add a windowed / incremental
  sweep (or a materialized per-ref check) before the book is large. Rationale:
  on-demand admin use today, but the nightly job will want bounded work.
- **PostHog funnel/liquidity dashboards are manual** — the events are emitted and
  the README has link placeholders; the dashboards themselves are built in the
  PostHog UI during the beta (they can't be provisioned from the repo). Rationale:
  exit-criterion "PostHog shows a complete funnel" is verified live in Phase 7.
- **Admin nav entry-point** — the `/admin` tree is reachable by URL and guarded by
  role, but there's no in-app link from the consumer shell for admins. Add a small
  role-gated "Admin" affordance in `AppShell`. Rationale: operators can bookmark
  `/admin` meanwhile; keeping the consumer shell clean was the Phase-6 priority.
