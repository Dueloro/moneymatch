# Architecture, Data Model & API Surface

Companion to [`00-README.md`](./00-README.md) (stack decisions live there).
This doc is the target-state design the phases build toward.

---

## 1. System overview

```
                    ┌────────────────────────────────────────────┐
                    │                 Postgres                    │
                    │  users · wallets · ledger_entries ·        │
                    │  linked_accounts · queue_tickets · matches │
                    │  solo_pools · tournaments · friendships ·  │
                    │  notifications · feature_flags · audit     │
                    └───────▲──────────────────────▲─────────────┘
                            │                      │ FOR UPDATE SKIP LOCKED
        JWT (Supabase)      │                      │
┌─────────┐  HTTPS  ┌───────┴────────┐     ┌───────┴────────┐    httpx    ┌─────────────┐
│ web SPA ├────────►│  FastAPI api   │     │ settlement     ├────────────►│ Lichess     │
│ (Vite)  │◄────────┤  (stateless)   │     │ worker (proc)  │             │ FaceIt      │
└─────────┘ JSON    └───────┬────────┘     └────────────────┘             │ OpenDota    │
                            │ httpx (profile fetch, brokering)            └─────────────┘
```

- **`apps/api`** — stateless FastAPI service. Verifies Supabase JWTs, owns all
  business logic, reads/writes Postgres. No in-memory state that matters
  (the PoC's in-memory `match_queue.py` moves to tables).
- **Settlement worker** — separate process, same codebase. Loop: claim due work
  (`matches` in `AWAITING_RESULT`, pools/tournaments past window end, expired
  queue tickets) with `FOR UPDATE SKIP LOCKED`, call the adapter, settle in a
  transaction, emit ledger entries + notifications. Runs every ~15 s; safe to
  run multiple instances.
- **Web SPA** — talks only to `apps/api` via the generated client. Auth session
  from Supabase JS; every API call carries the JWT. Client state = TanStack
  Query cache; **nothing durable in localStorage except the session**.
- **Host APIs** — accessed only from the server, only through adapters.
  `FACEIT_API_KEY` is server-side config (the PoC leaked no key client-side;
  keep it that way).

### Request patterns

- Reads: REST GET, cached client-side by TanStack Query with sensible
  `refetchInterval` on live surfaces (queue status 2 s, activity 10 s).
- Writes: POST intents carrying **ids only** (`{"pool_id": …}`), never amounts.
- Realtime: polling is fine for MVP (the worker makes state converge). A later
  SSE upgrade slots into the same endpoints; do not build websockets now.

---

## 2. Data model

Conventions: `id UUID PK default gen_random_uuid()`, `created_at/updated_at
timestamptz`, money in **integer cents**, all enums as Postgres enums or checked
varchars, FKs `ON DELETE RESTRICT` (nothing money-adjacent cascades).

### Identity

- **users** — `id`, `auth_id` (Supabase UID, unique), `username` (unique,
  citext), `email`, `residence_state` (2-letter, nullable until set), `dob_attested_18plus bool`,
  `role` (`user|admin`), `status` (`active|frozen|self_excluded`), `member_since`.
- **linked_accounts** — `id`, `user_id FK`, `game` (`chess.lichess|cs2.faceit|dota2.opendota`),
  `host_account_id`, `host_username`, `link_method` (`username|oauth`),
  `profile_snapshot jsonb` (last fetched SkillProfile), `linked_at`.
  Unique `(user_id, game)` **and** unique `(game, host_account_id)` — one host
  account binds to one user (immutable binding; rebind = admin action, audited).

### Money

- **wallets** — `id`, `user_id FK`, `currency` (`DEMO` now; `CASH`/`GEMS` later),
  `available_cents`, `escrow_cents`, `lifetime_net_cents`, unique `(user_id, currency)`.
  Balance columns are a **cache** maintained transactionally with ledger writes.
- **ledger_entries** (append-only; no UPDATE/DELETE — enforce with a trigger) —
  `id`, `wallet_id FK`, `entry_type`
  (`demo_deposit|demo_withdrawal|escrow_hold|escrow_release|payout|rake|refund|adjustment`),
  `amount_cents` (signed, applied to available), `escrow_delta_cents` (signed),
  `ref_type` (`match|solo_pool|tournament|admin|demo_rail`), `ref_id`,
  `balance_after_cents`, `memo`, `created_at`, `created_by`.
- **platform_ledger** — same shape, wallet-less, with an `account` column
  (chart of accounts, from the production launch plan §3.1): `platform:rake`
  (rake income) and `platform:promo` (funds every demo/signup credit, so promos
  never mint value silently). Every settlement writes rake here so
  `sum(payouts) + rake == sum(entries)` is checkable from the DB alone; the
  promo account makes the **global solvency invariant** checkable too:
  `sum(user available + escrow) == promo funding − rake` (demo money; at real
  money the deposits/withdrawals terms join the equation).
- **limits** (per user) — `daily_loss_cap_cents` (default $200), `daily_entry_cap_cents`
  (default $500), `max_concurrent_contests` (default 3), enforced **server-side**
  at escrow time (the PoC's `canJoin` tautology bug must not survive the port).

### Skill & audit substrate (from the challenge-engine / launch-plan proposals)

- **metric_models** — per `(user_id, game, metric)`: `mu`, `sigma`, `n`
  (sample size), `updated_at` — an EWMA mean/std-dev of per-match values over
  the last ~20 finished matches (half-life 10). Computed at link time,
  refreshed on every settlement and nightly. `n < 10` ⇒ the metric is
  **provisional** for that player (no stat duels or pool entries on it).
  Metrics are **rate-based only** (K/D, ADR, HS%, KDA, GPM — the typed
  allowlist); never raw totals, never anything outside the player's control.
- **baseline snapshots** — every match player / pool entry / tournament entry
  stores a `baseline_snapshot jsonb` (the metric model values used) **frozen at
  escrow time**, so bars and pairings can't be manipulated between join and
  play, and any dispute replays deterministically from stored inputs.
- **raw_payloads** — every host-API response used in a grading decision is
  persisted (`id`, `source`, `fetched_at`, `payload jsonb`, content hash) and
  referenced from `matches.outcome_detail` / entry grading records. Grading
  proof is an audit requirement, not a nicety.
- Settlement records carry an `engine_version` string (matchmaking / grading /
  bar-derivation versions) so disputes know exactly which rules produced a result.

### Play

- **queue_tickets** — `id`, `user_id`, `game`, `product` (`duel|pool|tournament`),
  `market` (see §3.1), `speed` (chess time control, nullable), `difficulty`
  (pools), `entry_cents`, `rating`, `baseline_snapshot`, `personal_bar`
  (pools), `tolerance_stage`, `state` (`waiting|matched|canceled|expired`),
  `created_at`, `expires_at`.
  Pairing runs in a transaction: lock compatible candidates, create the
  match/room (match-on-write — a compatible pair/room forms in one round trip).
- **matches** — `id`, `game`, `market`, `speed`, `entry_cents`, `rake_pct`,
  `pot_cents`, `prize_cents`, `rake_cents`, `state`
  (`PENDING → ACTIVE → AWAITING_RESULT → SETTLED | CANCELED | PUSHED`),
  `brokered bool`, `host_game_id`, `matched_at`, `window_ends_at`,
  `winner_user_id`, `outcome_detail jsonb`, `resolved_at`.
  PoC parity: `PUSHED` = tie → both refunded, no rake ("tie = push" in design).
- **match_players** — `match_id FK`, `user_id FK`, `linked_account_id FK`,
  `color` (chess), `play_url`, `confirmed_at`, `payout_cents`, `stat_line jsonb`
  (for stat-race markets: the graded K/D, ADR, HS% values shown in Activity).
- **solo_pools** — queue-matched rooms (see Phase 4): `id`, `game`, `metric`,
  `difficulty` (`easy|medium|hard`), `room_bar` (server-derived average of
  members' personal bars), `entry_cents`, `rake_pct`,
  `window_starts_at/ends_at`, `min_entrants`, `state`
  (`OPEN → LOCKED → SETTLED | CANCELED`), totals.
- **solo_entries** — `pool_id`, `user_id`, `linked_account_id`,
  `personal_bar`, `baseline_snapshot`, `status`
  (`LOCKED|CLEARED|MISSED|REFUNDED`), `telemetry jsonb` (server-fetched),
  `raw_payload_id`, `payout_cents`.
- **tournaments / tournament_entries** — matchmade single-metric rooms
  (see Phase 4): `ranking_metric`, `entry_cents`, `prize_split jsonb`
  (default 50/30/20), `field_size`/`min_field`, window timestamps; entries
  carry `baseline_snapshot`, `score` (first-N average, server-graded), `rank`,
  `payout_cents`. Single-elim brackets are cut from MVP.

### Social & ops

- **friendships** — `user_id`, `friend_id`, `state` (`pending|accepted|blocked`),
  unique ordered pair.
- **challenges** — direct friend challenges: `id`, `challenger_id`, `challengee_id`
  (nullable + `invite_token` for link invites), `game`, `market`, `entry_cents`,
  `state` (`sent|accepted|declined|expired`), on accept → creates a `match`.
- **notifications** — `user_id`, `kind` (`match_found|settled|challenge|refund|system`),
  `payload jsonb`, `read_at`. Backs the Inbox screen.
- **feature_flags** — `key`, `enabled bool`, `payload jsonb` (e.g. per-game
  enable, `settlement_paused`, `queue_paused`).
- **admin_audit** — every admin action: `admin_id`, `action`, `target`, `detail jsonb`.
- **events** — server-side product analytics mirror (PostHog is primary;
  this table is the cheap backup and the queue-health source).

---

## 3. Domain rules

### 3.1 Markets (what you can wager on) — from the design PDF

Per game, a small fixed list; **no free-form props** (legal guardrail):

| Game | Markets | Resolution |
| --- | --- | --- |
| CS2 (`cs2.faceit`) | `kd_ratio`, `adr`, `headshot_pct`, `win_next` | Both players' **next finished FaceIt match** after `matched_at`, within 24 h. Stat race: higher stat wins; equal → push. `win_next`: win beats loss; tie/both-same → push. |
| Chess (`chess.lichess`) | `win_h2h` (brokered direct game), per time control | Brokered Lichess game between the two bound accounts; draw → push. |
| Dota 2 (`dota2.opendota`) | `win_next`, `kda_ratio`, `gpm` | Next finished match after `matched_at`, within 24 h. |

Stat-race markets between two players are **peer-to-peer stat duels** (both
stake, better stat takes the pot minus rake) — this is the design's
"K/D ratio · ×1.80" card. The `×1.80` is *derived*: `2 × entry × (1 − rake) / entry`.
Never configured as an odds line. Pairing fairness comes from the duel-forecast
model (Phase 3): `P(a beats b) = Φ((μa − μb) / √(σa² + σb²))` held near 50/50,
since equal stakes forbid handicaps. Unresolvable within the window (no
qualifying match, private profile, host outage) → CANCELED, full refund, zero rake.

Chess brokering detail (from the launch plan §6.1): the server creates a
**Lichess open challenge restricted to the two linked usernames**
(`POST /api/challenge/open` with `users=a,b`) — no OAuth needed at MVP, both
players get the same link but only those two accounts can occupy the seats, and
settlement grades **that specific game id** (no "next qualifying game" inference).

### 3.2 Money flows

- **Escrow:** join/enter moves `entry` available → escrow (ledger `escrow_hold`)
  after server-side checks: balance, daily caps, concurrent-contest cap,
  geo-fence (`residence_state` not in the 14 excluded states — config table, not
  code constant), per-game flag enabled, account linked for that game.
- **Settle (H2H):** winner gets `prize = pot − rake` (escrow_release + payout),
  loser's escrow releases to zero, rake row hits `platform_ledger`.
- **Push/cancel:** both escrows release back to available in full; **no rake**.
- **Pools:** clearers split `pool − rake` equally (integer division, remainder
  cents to rake); nobody clears → full refund, zero rake; under `min_entrants`
  at lock time → CANCELED, refund.
- **Tournaments:** rank by metric; top-N split per `prize_split` (renormalize if
  fewer finishers); unverifiable entrants refunded off the top.
- **Demo rails:** `demo_deposit` (the Wallet "Add funds" $10/$25/$50/$100) and
  `demo_withdrawal` write real ledger rows tagged `ref_type='demo_rail'`. At
  real-money launch these are replaced by processor-driven events — same ledger.

### 3.3 Settlement worker contract

Every cycle, in separate transactions per item:

1. `matches` in `ACTIVE/AWAITING_RESULT` past a poll interval → adapter
   `resolve_match()` → `SETTLED/PUSHED/still-waiting`; past `window_ends_at` → `CANCELED`.
2. `solo_pools`/`tournaments` past `window_ends_at` → fetch telemetry per entrant
   via adapter (server-side), grade, settle.
3. `queue_tickets` past `expires_at` → `expired` (escrow was never taken for
   waiting tickets — escrow happens at match confirm).
4. Reconciliation assertions: per touched ref,
   `sum(ledger payouts) + rake == sum(entries)`; nightly, the **global solvency
   check** `sum(user available + escrow) == promo funding − rake`. On any
   violation → set `settlement_paused`, alert Sentry, stop. **Fail closed.**

### 3.4 Failure-mode matrix (every row needs a tested code path)

Adapted from the production launch plan §6.2 — the unifying rule is the
**watchdog principle**: every non-terminal state carries a max age, and expiry
always resolves toward *refund*, never toward loss. No object is ever stuck; no
cent is ever stranded in escrow.

| Failure | Handling |
| --- | --- |
| Host API down / 5xx during settlement | Match stays `AWAITING_RESULT`; worker retries with backoff. Outage does not consume the window (`window_ends_at` extends by downtime). Beyond a 24 h hard ceiling → CANCELED, full refund. |
| No qualifying game in the window | CANCELED, full refund, zero rake. |
| Identical stats / chess draw / both-win | PUSH: full refund, zero rake. |
| Opponent never plays (one-sided stat duel) | The player who played wins by forfeit, but **only after** the full window plus a disclosed grace period; the forfeit rule is printed on the slip before entry. |
| Unlink / host ban mid-contract | Unlink is blocked while contests are in flight; a host cheat-ban pre-settlement → CANCELED + refund + risk flag. |
| Double-join / double-confirm race | Transactional re-read; second actor fails cleanly. |
| Worker double-fire | Idempotent transitions: no-op unless state is claimable; ledger service rejects a second payout for the same ref. |
| Queue ticket / challenge orphaned | TTL + worker expiry → cancel + refund. |
| Room/field never fills | Widening ladder exhausts → offer start-at-minimum or cancel + refund. Rooms never form below minimum. |
| Room bar / pairing disputed post-settlement | `room_bar`, every `personal_bar`, and pairings replay deterministically from frozen `baseline_snapshot`s + `engine_version` — the audit is a pure-function re-run. |
| Ledger drift / invariant breach | Reconciliation cron: alert + auto-flip kill switches. Fail closed. |

---

## 4. API surface (v1)

All under `/api/v1`, JWT-authed unless noted. Errors: RFC-7807-style
`{code, message, detail}`. Responses come from Pydantic schemas → OpenAPI → TS client.

```
GET    /health                          # public: service + registered games + flags

# me & profile
GET    /me                              # user, wallet snapshot, limits, flags
PATCH  /me                              # residence_state, username (once), limits (lowering instant; raising delayed)
POST   /me/self-exclude

# linking
GET    /links                           # linked accounts + profile snapshots
POST   /links {game, username}          # server verifies via adapter, binds
DELETE /links/{game}                    # admin-gated in MVP (immutable bindings)
GET    /links/{game}/profile            # refresh snapshot

# wallet
GET    /wallet                          # balances + recent ledger
GET    /wallet/ledger?cursor=
POST   /wallet/demo-deposit {amount_preset}     # $10|$25|$50|$100 presets only
POST   /wallet/demo-withdrawal {amount_cents}

# play (H2H)
GET    /play/markets?game=              # market defs + derived multiplier + queue depth
POST   /play/queue {game, market, speed?, entry_preset}   # $5|$10|$25
GET    /play/queue/status
DELETE /play/queue
POST   /play/matches/{id}/confirm       # escrow happens here (both confirm → broker+activate)
GET    /play/matches/{id}
GET    /play/waiting                    # design's "Waiting to play" list (open tickets of others)
POST   /play/waiting/{ticket_id}/match  # take the other side directly

# pools
GET    /pools?game=                     # open pools by tier + your entries
POST   /pools/{id}/enter
GET    /pools/{id}

# tournaments
GET    /tournaments?game=
POST   /tournaments/{id}/enter
GET    /tournaments/{id}                # standings (live during window)

# social
GET    /friends                         # + presence-lite (last_seen)
POST   /friends {username_or_code}
POST   /friends/{id}/accept | /decline | DELETE
POST   /challenges {friend_id?, game, market, entry_preset}   # or link invite
POST   /challenges/{id}/accept | /decline
GET    /challenges/token/{invite_token}         # public preview → sign-in → accept

# activity & inbox
GET    /activity                        # unified: matches, pools, tournaments (design Activity screen)
GET    /leaderboard                     # real users, ROI-ranked (PoC bot field dropped)
GET    /notifications  ·  POST /notifications/read

# admin (role=admin)
GET    /admin/users · GET /admin/users/{id} · POST /admin/users/{id}/freeze
GET    /admin/contests?state=&game=
POST   /admin/matches/{id}/resettle | /void
GET    /admin/ledger?user= · GET /admin/reconciliation
GET/PUT /admin/flags
GET    /admin/queue                     # depth, wait times, expiry rate
```

Legacy PoC endpoints that do **not** carry over: client-posted settle bodies
(`POST /api/contracts/settle` with full Contract), client-posted telemetry
(`/api/solo/pools/settle`), dev FaceIt lab routes (rebuilt as admin-only if needed).
