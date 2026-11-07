# Architecture

How Money Match is built. Product rules live in
[`PRODUCT_CONTEXT.md`](./PRODUCT_CONTEXT.md). Paths below are relative to
`apps/api/src/moneymatch_api/` unless they start at the repo root.

## System

```
Browser (React SPA, Vercel) ──HTTPS──▶ FastAPI API (Render web) ──▶ Postgres (Render)
  signs in with Supabase Auth            verifies the JWT,               ▲
  sends intents with ids                 owns every number               │
                                                                         │
                           Settlement worker (Render worker) ────────────┘
                             polls Lichess, grades, settles, reconciles
```

- The browser talks only to the API. It never touches the database.
- API and worker are the same Python package and Docker image
  (`apps/api/Dockerfile`), started with different commands (`render.yaml`).
- Types flow Pydantic → OpenAPI → generated TS client (`packages/api-client`).
- PostHog (analytics), Sentry (errors) and Resend (email) are external services.

## Invariants

From `PRODUCT_CONTEXT.md` §6. Any change to money, matches or settlement keeps all six.

| # | Invariant | Enforced in |
|---|---|---|
| 1 | `sum(payouts) + fee = sum(entries)` on every settlement | `services/money_math.py:Split.__post_init__`; `services/reconciliation_service.py:check`, called after each settle by `_assert_reconciled` in `services/match_lifecycle.py`, `services/pool_engine.py`, `services/tournament_engine.py` |
| 2 | The server owns every number | Request schemas carry ids and preset choices only (`schemas/`); entries must be in `ENTRY_PRESETS_CENTS` (`services/matchmaking.py:enqueue`, `_validate_bucket` in `services/pool_engine.py` and `services/tournament_engine.py`); amounts come from `services/money_math.py` |
| 3 | Results come from the game's API | `services/grading.py:grade` (head-to-head, via the adapter's `match_winner`); `services/telemetry_fetch.py:grade_pool` / `grade_tournament`. No endpoint accepts a result |
| 4 | Fee only when a pot pays out | `services/match_lifecycle.py:settle` (push/cancel/friendly refund, no rake); `services/pool_engine.py:settle_pool` (nobody clears → full refund, zero rake) |
| 5 | Integer cents, append-only ledger | `BigInteger` money columns and `mm_reject_mutation` triggers on `ledger_entries`, `platform_ledger`, `raw_payloads` (`apps/api/migrations/versions/0001_baseline.py`); all writes through `services/wallet_service.py:_apply`; `apps/api/tests/test_no_floats_in_money_path.py` |
| 6 | The platform never plays against users | The only platform accounts are `platform:rake` and `platform:promo` (`models/wallet.py:PLATFORM_ACCOUNTS`); payouts come only from escrowed entries |

Fail closed: if reconciliation breaks after a settle, the worker raises
`ReconciliationError`, sets `settlement_paused`, and stops settling for
everyone (`workers/settlement_worker.py:_halt_on_breach`). Unverifiable
entrants are refunded, never guessed.

## Money path

1. **Escrow.** `wallet_service.escrow_hold` moves the entry from available to
   escrow when the contest forms: on confirm for head-to-head
   (`match_lifecycle.confirm`), on room formation for pools
   (`pool_engine._form_room`), on field formation for tournaments
   (`tournament_engine._form_field`). Waiting in a queue holds nothing.
2. **Settle.** The worker grades the contest, then `escrow_release` consumes the
   stakes, `payout` pays winners, `rake` books the fee to `platform:rake`. Or
   `refund` returns every entry with no fee.
3. **Rake.** `money_math.rake_for` floors `pot × rake_bps / 10000`
   (`DEFAULT_RAKE_BPS = 1000`, 10%). Leftover cents from splitting go to the
   rake, so nothing is minted or lost.
4. **Ledger.** Every move is one `ledger_entries` row, written in the same
   transaction that updates the cached balances on `wallets`. Play money comes
   from `platform:promo` through the same ledger.

## Adapter seam

Every game plugs in through `adapters/base.py:GameAdapter`: `link_account`,
`fetch_profile`, `poll_eligible_games`, `create_match`, `match_winner`,
`live_match`. Callers resolve adapters with `adapters/registry.py:get(game_id)`,
never by import. Settlement sees normalized `NormGame` / `TelemetrySample`,
never raw host JSON.

Chess (`adapters/chess_lichess.py`, id `chess.lichess`) is the only adapter.
Its host client is `services/hosts/lichess.py`. Lichess needs no API key for
the endpoints used.

Adding a title means one adapter plus its constants and markets. Start from
[`future-expansion/README.md`](../future-expansion/README.md).

## Play models

| Model | How it works | Settles |
|---|---|---|
| Head-to-head | Matched by Elo band; the API opens a Lichess challenge restricted to both players (`create_match`) and grades that game id | Winner takes pot minus fee; draw or unfinished → refund |
| Solo pool | 3–4 players at a similar personal bar, metric `chess_moves` (lower is better, must be a win), 24h window | Clearers split pot minus fee; nobody clears → full refund |
| Tournament | Field of 6–10, aggregate metric (`chess_win_streak`, `chess_wins`, `chess_fastest_win`), 48h window | Top places split 50/30/20 minus fee |

Friends, challenges, invites and rematches create head-to-head matches
(`services/challenge_service.py`, `matchmaking.create_challenge_match`).
Friendly matches are zero-fee and refund both entries.

Numbers live in `constants.py` (`POOL_*`, `TOURNAMENT_*`).

## Matchmaking

Queue tickets live in `queue_tickets`, claimed with `FOR UPDATE SKIP LOCKED`.
Two tickets pair when their ratings are within the band
(`services/matchmaking.py:_chess_band`): 100 Elo, widening by 12 per second of
waiting, capped at 800 (`CHESS_BASE_BAND`, `CHESS_BAND_GROWTH_PER_SEC`,
`CHESS_MAX_BAND`). The wider of the two tickets' bands applies, and the closest
rating wins. Recent repeat pairings are blocked (`can_pair`).

## Worker loop

`workers/settlement_worker.py:run_forever`, every 15 s
(`WORKER_POLL_INTERVAL_SECONDS`). Each unit of work runs in its own
transaction, claimed with `FOR UPDATE SKIP LOCKED`, so a crash leaves it
re-claimable and nothing double-settles. `run_cycle`:

1. Write the heartbeat (`worker_heartbeat` flag).
2. Stop here if `settlement_paused` is on.
3. Grade and settle due matches, pools, tournaments. A Lichess outage extends
   the window; past the hard ceiling the contest cancels and refunds.
4. Refresh tournament standings and live snapshots.
5. Expire unconfirmed matches (refunding whoever escrowed), stale tickets,
   and old challenges.
6. If `queue_paused` is on, cancel all waiting tickets.

Once a day it also runs `workers/nightly.py` (metric-model refresh,
sandbagging sweep, win-streak detector).

## Data model

Models in `models/`; schema in `apps/api/migrations/versions/0001_baseline.py`.

| Table | Holds |
|---|---|
| `users` | One per Supabase user: username, state, role, KYC status, friend code |
| `wallets` | Cached balances (available, escrow, lifetime net); never written outside `wallet_service` |
| `ledger_entries` | Append-only wallet money moves, the source of truth |
| `platform_ledger` | Append-only `platform:rake` and `platform:promo` rows |
| `limits` | Per-user staking caps, with delayed raises |
| `linked_accounts` | Bound Lichess accounts; soft-unbind keeps history |
| `metric_models` | Per user/game/metric skill model (μ/σ) behind personal bars |
| `raw_payloads` | Append-only raw host JSON kept as settlement evidence |
| `queue_tickets` | The matchmaking queue (all three play models) |
| `matches` / `match_players` | Head-to-head contests and their two seats |
| `solo_pools` / `solo_entries` | Pools and their entrants |
| `tournaments` / `tournament_entries` | Tournaments and their entrants |
| `friendships` / `challenges` | Friends and single-use invite tokens |
| `conversations` / `conversation_members` / `messages` | Chat |
| `notifications` / `push_subscriptions` | In-app notifications and Web Push |
| `risk_flags` | Sandbagging and win-streak detector output |
| `disputes` | Operator-reviewed disputes (never override the ledger) |
| `feature_flags` | Kill switches, geo config, worker heartbeat |
| `admin_audit` | One row per admin action |
| `live_snapshots` | Cached in-progress game state for Activity |

Migrations are forward-only. Ship each schema change with its migration.

## Auth

Supabase Auth handles sign-in (email and Google). The web app sends the
Supabase access token as a bearer token. The API verifies it in
`auth.py:verify_token`: HS256 with `SUPABASE_JWT_SECRET` if set, otherwise the
project's JWKS (RS256/ES256). `dependencies.py:get_current_user` maps the token
to a `users` row (created on first sight); `require_admin` gates `/admin`.
Everything else about the user lives in our database.
