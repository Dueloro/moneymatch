# Chess-Only Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce Money Match to a sleek, chess-only (Lichess), no-money product that matches `docs/PRODUCT_CONTEXT.md`, with PUBG/Dota 2 parked in `future-expansion/`, CS2 and all demo scaffolding deleted, the worker deployed properly, and docs cut to a small accurate set.

**Architecture:** Keep the `GameAdapter` seam and every money invariant intact; chess becomes the only registered adapter and `win_h2h` the only market kind. The three play models (head-to-head, solo pools on `chess_moves`, tournaments) and the social layer (friends, challenges, invites, rematches, chat, leaderboard, push, disputes) stay. Everything else that exists only for other games, for the demo account, or for the CS2 sidecar is moved or deleted. A single forward migration cleans the schema; no migration history is rewritten (prod has live data).

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic (Python 3.12, `uv`), Postgres 16, React 18 + Vite + Tailwind + TanStack Query, pnpm workspace, Render (API/worker) + Vercel (web), Supabase Auth, PostHog, Sentry, Resend.

**This file is temporary.** It lives in `docs/superpowers/`, which Task 8.3 deletes. Move it out first if you want to keep it.

---

## Decisions locked in (from the user, 2026-11-06)

| Area | Decision |
|---|---|
| Games | Chess (Lichess) only. PUBG + Dota 2 code/docs → `future-expansion/`. CS2 + `gc-sidecar/` deleted outright (recoverable from tag `pre-chess-only`). |
| Play models kept | Head-to-head, solo pools, tournaments |
| Social kept | Friends, challenges, invite links, rematches, chat, leaderboard, push notifications, disputes |
| Removed | Demo login, simulated adapter (`DEMO_SIMULATE`), test/practice opponents, game selection / `active_games`, Steam OpenID, all CS2 code |
| Business/legal docs | Useful ones → `docs-export/` (user exports, then we delete); stale ones deleted |
| UI/UX | Sleek, on-brand polish pass on every remaining screen. No new visual language: extend the existing token system in `apps/web/src/styles/index.css` |
| Database | The old Render Postgres expired (free tier, deleted after inactivity). **No prod data to preserve.** Users re-provision automatically on next sign-in (`get_or_create_user`); they relink Lichess and get a fresh play-money wallet. |
| Migrations | Fresh DB, so squash all 28 migrations into one baseline (Task 4.1). |
| Hosting | Rebuild Render from scratch on the user's personal account ($50 credit) via the Blueprint in `render.yaml`; move to a corporate account after funding. API served at `api.dueloro.com` (custom domain) so the move is a DNS change. Try to reclaim `moneymatch.onrender.com` too. |
| Seed script | `scripts/seed_demo.py` and `make seed` deleted |

**Kept on purpose (not bloat):** `payments/` and `kyc/` interfaces + their `demo` stubs (roadmap items 2–3; real money stays OFF), the play-money wallet (`DEMO_DEPOSIT_PRESETS_CENTS` is play money, not demo login), the e2e auth seam (`apps/web/src/lib/e2eAuth.ts`, `/dev/e2e/token`, dev-only), the metric/baseline/fairness machinery (it powers chess solo pools via `chess_moves`).

**Folder name:** `future-expansion/` (hyphen, not a space, so shell/CI paths don't break).

---

## File structure after this plan

```
apps/api/src/moneymatch_api/
  adapters/            base.py, chess_lichess.py, registry.py           (cs2/pubg/dota2/simulated gone)
  services/hosts/      _client.py, errors.py, lichess.py                (steam/pubg/opendota gone)
  services/            cs2_*, gc_client, sharecode, steam_openid,
                       demo_mode, demo_simulation, test_opponents       → deleted / moved
  routers/             cs2.py, demo.py                                   → deleted
  models/              cs2.py, demo_simulation.py                        → deleted
  migrations/versions/ 0001_baseline.py                                 (squashed; replaces 0001–0027)
apps/web/src/          cs2/, DemoHandles, DemoSignInPage, demoAuth,
                       GameSelectOverlay, useGameSelection, steamReturn,
                       SteamCallbackPage, useCs2, GameTabs (if unused)  → deleted
future-expansion/
  README.md            what this is, how to revive a game, "not run, not tested"
  pubg/                adapter, host client, tests, specs/plans
  dota2/               adapter, host client, tests
  steam/               OpenID + Steam Web API host client, tests (needed by any Steam title)
  multi-game-core/     win_next + stat_race market kinds, per-game constants, docs
docs/                  README.md, PRODUCT_CONTEXT.md, architecture.md, development.md,
                       runbook.md, design-guidelines.md
docs-export/           business + legal docs for the user to export, then delete
supabase/email-templates/   (moved from docs/email-templates)
```

---

## Phase 0 — Safety net and baseline

### Task 0.1: Branch and tag

- [ ] **Step 1:** Create the tag and branch from current HEAD.

```bash
cd /Users/shreyansh/Desktop/moneymatch
git tag pre-chess-only
git switch -c refactor/chess-only
git push origin pre-chess-only
```

- [ ] **Step 2:** Confirm: `git describe --tags` prints `pre-chess-only`.

### Task 0.2: Test baseline

- [ ] **Step 1:** Start Docker Desktop, then the throwaway test DB on :5433 (see memory: no compose service for it).

```bash
docker run -d --name mm-testdb -e POSTGRES_USER=moneymatch -e POSTGRES_PASSWORD=moneymatch \
  -e POSTGRES_DB=moneymatch_test -p 5433:5432 postgres:16
until pg_isready -h localhost -p 5433; do sleep 1; done
```

- [ ] **Step 2:** Run both suites and save the output.

```bash
make test-api 2>&1 | tail -40 > /tmp/claude-scratch-baseline-api.txt
make test-web 2>&1 | tail -40 > /tmp/claude-scratch-baseline-web.txt
```
(Use the session scratchpad dir instead of /tmp in practice.)

- [ ] **Step 3:** Record pass/fail counts and any pre-existing failures at the top of this plan under "Baseline". Pre-existing failures are not ours to fix unless they're in kept code.

---

## Phase 1 — (removed)

The prod database expired, so there is no production data to inventory, refund, or preserve. That removes the need for an `is_system` flag, an "Archived game" fallback, or permissive `game` check constraints for legacy rows.

---

## Phase 2 — Park PUBG / Dota 2 in `future-expansion/`

Use `git mv` throughout so history follows the files.

### Task 2.1: Move game code, tests and docs

**Files:**
- Move: `apps/api/src/moneymatch_api/adapters/pubg.py` → `future-expansion/pubg/adapter.py`
- Move: `apps/api/src/moneymatch_api/services/hosts/pubg.py` → `future-expansion/pubg/host_client.py`
- Move: `apps/api/tests/test_pubg_adapter.py`, `test_pubg_rate_limit.py`, `test_pubg_settlement.py` → `future-expansion/pubg/tests/`
- Move: `docs/superpowers/specs/2026-08-12-pubg-completion-design.md`, `docs/superpowers/plans/2026-08-12-pubg-completion.md` → `future-expansion/pubg/docs/`
- Move: `apps/api/src/moneymatch_api/adapters/dota2_opendota.py` → `future-expansion/dota2/adapter.py`
- Move: `apps/api/src/moneymatch_api/services/hosts/opendota.py` → `future-expansion/dota2/host_client.py`
- Move: `apps/api/tests/test_dota2_opendota_adapter.py` → `future-expansion/dota2/tests/`
- Move: `apps/api/src/moneymatch_api/services/steam_openid.py`, `services/hosts/steam.py` → `future-expansion/steam/`
- Move: `apps/api/tests/test_steam_host.py` → `future-expansion/steam/tests/`
- Move: `docs/adding-a-game.md`, `docs/adding-a-market-kind.md` → `future-expansion/multi-game-core/docs/`

- [ ] **Step 1:** Run the moves.

```bash
cd /Users/shreyansh/Desktop/moneymatch
mkdir -p future-expansion/{pubg/tests,pubg/docs,dota2/tests,steam/tests,multi-game-core/docs}
A=apps/api/src/moneymatch_api; T=apps/api/tests
git mv $A/adapters/pubg.py future-expansion/pubg/adapter.py
git mv $A/services/hosts/pubg.py future-expansion/pubg/host_client.py
git mv $T/test_pubg_adapter.py $T/test_pubg_rate_limit.py $T/test_pubg_settlement.py future-expansion/pubg/tests/
git mv docs/superpowers/specs/2026-08-12-pubg-completion-design.md docs/superpowers/plans/2026-08-12-pubg-completion.md future-expansion/pubg/docs/
git mv $A/adapters/dota2_opendota.py future-expansion/dota2/adapter.py
git mv $A/services/hosts/opendota.py future-expansion/dota2/host_client.py
git mv $T/test_dota2_opendota_adapter.py future-expansion/dota2/tests/
git mv $A/services/steam_openid.py future-expansion/steam/openid.py
git mv $A/services/hosts/steam.py future-expansion/steam/host_client.py
git mv $T/test_steam_host.py future-expansion/steam/tests/
git mv docs/adding-a-game.md docs/adding-a-market-kind.md future-expansion/multi-game-core/docs/
```

### Task 2.2: Extract the multi-game core pieces before deleting them from `apps/api`

The non-chess market kinds and per-game constants are entangled in shared files. Copy (not move) the relevant blocks into `future-expansion/multi-game-core/` so they survive, then Phase 3 deletes them from the live code.

- [ ] **Step 1:** Create `future-expansion/multi-game-core/markets_non_chess.py` containing, verbatim, the CS2-excluded `MarketDef` entries for Dota 2 and PUBG from `services/markets.py`, plus `KIND_WIN_NEXT`/`KIND_STAT_RACE`.
- [ ] **Step 2:** Create `future-expansion/multi-game-core/constants_non_chess.py` with every Dota 2 / PUBG entry from `constants.py` (`GAME_DOTA2_OPENDOTA`, `GAME_PUBG_STEAM`, their keys in `GAME_RATE_METRICS`, `GAME_HISTORY_FLOOR`, `POOL_METRICS`, `TOURNAMENT_METRICS`, any metric-direction maps).
- [ ] **Step 3:** Copy the `win_next` / `stat_race` grading branches from `services/grading.py` (and wherever `match_lifecycle.py`/`settlement_worker.py` branch on those kinds) into `future-expansion/multi-game-core/grading_non_h2h.py`, with a header comment naming the original file and commit.

### Task 2.3: Write `future-expansion/README.md`

- [ ] **Step 1:** Write:

```markdown
# Future expansion

Code and docs for titles we are not shipping yet. **Nothing in this folder is
imported, run, linted, or tested.** It is a reference snapshot taken at tag
`pre-chess-only` (2026-11-06), when Money Match went chess-only.

| Folder | What it is |
|---|---|
| `pubg/` | PUBG adapter (official PUBG API), host client with rate limiting, settlement tests, design spec |
| `dota2/` | Dota 2 adapter via OpenDota, host client, tests |
| `steam/` | Steam OpenID sign-in + Steam Web API client (ban checks). Any Steam title needs it |
| `multi-game-core/` | The `win_next` and `stat_race` market kinds, per-game constants, and the "adding a game / market kind" guides |

## Reviving a title

1. Read `multi-game-core/docs/adding-a-game.md`. The adapter interface it
   describes still exists in `apps/api/src/moneymatch_api/adapters/base.py`.
2. Move the adapter back into `apps/api/src/moneymatch_api/adapters/`, register
   it in `adapters/registry.py`, and restore its constants and markets.
3. If it uses `win_next` or `stat_race`, restore those kinds from
   `multi-game-core/` first. Chess only uses `win_h2h`.
4. Move its tests back and get them green against current code. Expect drift:
   this code stopped being maintained on 2026-11-06.

CS2 is intentionally absent. Its Game Coordinator sidecar approach was dropped.
If CS2 returns, start from the FACEIT Data API instead; the old code is at tag
`pre-chess-only`.
```

- [ ] **Step 2:** Make sure tooling ignores the folder: add `future-expansion` to the ruff/mypy/pytest excludes in `apps/api/pyproject.toml` (it's outside `apps/api` so pytest won't collect it; verify ruff config at repo root, if any) and to `.prettierignore` / eslint ignores if they glob the repo root.

- [ ] **Step 3:** Commit.

```bash
git add -A && git commit -m "chore: park PUBG, Dota 2 and Steam code in future-expansion/"
```

(The API will not import cleanly until Phase 3 finishes. Phases 2–3 land in one PR.)

---

## Phase 3 — Backend: chess only

Work file by file. After each task run `cd apps/api && uv run python -c "import moneymatch_api.main"` and `uv run ruff check .` to catch dangling imports early. Full test runs happen at the end of each task.

### Task 3.1: Delete CS2 and the sidecar

- [ ] **Step 1:** Delete.

```bash
A=apps/api/src/moneymatch_api; T=apps/api/tests
git rm -r gc-sidecar
git rm $A/routers/cs2.py $A/adapters/cs2_steam.py $A/models/cs2.py \
  $A/services/cs2_baseline.py $A/services/cs2_chain.py $A/services/cs2_matches.py \
  $A/services/cs2_prior.py $A/services/cs2_submission.py $A/services/gc_client.py $A/services/sharecode.py
git rm $T/test_cs2_*.py $T/test_sharecode.py $T/test_gc_health_status.py $T/test_gc_sidecar_url.py
git rm scripts/demo/cs2_dryrun.py scripts/demo/mock_gc_sidecar.py scripts/demo/verify_cs2_settlement.py
```

- [ ] **Step 2:** Remove references:
  - `main.py`: drop `cs2` from the router import list and the `app.include_router(cs2.router, ...)` line.
  - `models/__init__.py`: drop the cs2 model imports.
  - `workers/settlement_worker.py`: delete `_sync_share_chains` (lines ~358–387) and its call in `run_cycle` (~line 674).
  - `routers/health.py`: remove any GC sidecar health field (search `gc`).
  - `config.py`: delete `steam_api_key`, `steam_openid_realm`, `steam_openid_return_url`, `gc_sidecar_url`, `gc_shared_secret`, `valve_chain_enabled`, `pubg_api_key`, `pubg_rate_limit_per_min`, and any prod-validation that references them. Keep the `web_origin` prod check.
- [ ] **Step 3:** `grep -rn -i -E "cs2|sharecode|gc_|valve|steam|pubg|dota|opendota" apps/api/src` → only expected hits are in `constants.py`/`markets.py`/`registry.py` (handled in 3.2). Fix anything else.

### Task 3.2: Collapse to one game and one market kind

**Files:** `constants.py`, `services/markets.py`, `adapters/registry.py`, `services/grading.py`, `services/match_lifecycle.py`, `services/metric_models_service.py`, `services/feature_flags.py`, `services/live_activity_service.py`, `services/dispute_service.py`, `models/skill.py`, `models/dispute.py`, `workers/settlement_worker.py`

- [ ] **Step 1:** `constants.py`: remove `GAME_CS2_STEAM`, `GAME_PUBG_STEAM`, `GAME_DOTA2_OPENDOTA` and every dict/tuple entry keyed by them. `REGISTERED_GAMES` becomes `(GAME_CHESS_LICHESS,)`. Keep the `game` concept everywhere (PRODUCT_CONTEXT §4: don't hard-code assumptions that block future titles).
- [ ] **Step 2:** `markets.py`: keep `KIND_WIN_H2H` and the single chess `MarketDef`. Delete `KIND_WIN_NEXT`, `KIND_STAT_RACE`, the `metric` field if only stat races used it (check `grep -rn "\.metric\b"` first), and rewrite the module docstring to describe one kind.
- [ ] **Step 3:** Delete every `win_next` / `stat_race` branch in `grading.py`, `match_lifecycle.py`, `settlement_worker.py` (they were copied in Task 2.2). Where a branch was `if kind == KIND_WIN_H2H: ... else: ...`, keep the H2H body unconditionally.
- [ ] **Step 4:** `adapters/registry.py`: register only `ChessLichessAdapter`; delete the `demo_simulation` wrapping (lines ~33–47).
- [ ] **Step 5:** Fix the remaining one-line references the grep found in `metric_models_service.py`, `live_activity_service.py`, `dispute_service.py`, `models/skill.py`, `models/dispute.py` (each is a game literal in a comment, check constraint, or label map; reduce to chess).
- [ ] **Step 6:** Narrow any check constraint listing allowed `game` values to `chess_lichess` only (the DB is fresh).

### Task 3.3: Remove demo login, simulated adapter, test opponents

- [ ] **Step 1:** Delete.

```bash
A=apps/api/src/moneymatch_api; T=apps/api/tests
git rm $A/routers/demo.py $A/services/demo_mode.py $A/services/demo_simulation.py \
  $A/services/test_opponents.py $A/adapters/simulated.py $A/models/demo_simulation.py
git rm $T/test_demo_escape_hatch.py $T/test_demo_login.py $T/test_demo_reset.py \
  $T/test_pool_dummy_forfeit.py $T/test_tournament_practice_field.py
git rm scripts/demo/verify_escape_hatch.py; rmdir scripts/demo 2>/dev/null || true
```

- [ ] **Step 2:** Remove references:
  - `main.py`: delete the `demo_login_enabled` block (~lines 172–179).
  - `auth.py`: delete the `DEMO_JWT_SECRET` verification path; JWTs come only from Supabase (and the dev-only e2e token if that uses a separate path; check).
  - `constants.py`: delete `DEMO_AUTH_ID`, `DEMO_EMAIL`, `DEMO_USERNAME`, `DEMO_RESIDENCE_STATE`, `DEMO_JWT_SECRET`.
  - `config.py`: delete `demo_login_enabled`, `demo_simulate_enabled`.
  - `routers/play.py` (~248), `routers/pools.py` (~185), `routers/tournaments.py` (~231): delete the `if test_opponents.is_enabled(user): ...fill_*` blocks and imports.
  - `workers/settlement_worker.py` (~145): `demo_mode.rated_only_for(...)` → production behaviour is "rated games only"; replace with the constant `True` semantics (inline: rated only) and delete the import.
  - `services/leaderboard.py` (~36, ~107): delete the `test_opponents.test_user_filter()` predicate and the import.
  - Settlement code calling `test_opponents.graded_as_failed` / `clears_its_bar` / `is_practice_opponent`: `grep -rn "test_opponents\|graded_as_failed\|clears_its_bar" apps/api/src` and delete those branches.
  - `models/__init__.py`: drop `SimulatedMatch`.
- [ ] **Step 3:** `test_pool_clearing_opponent.py` used practice opponents. Rewrite it to create two real users with factory-built linked Lichess accounts and stubbed host results (follow the pattern in `test_pool_engine.py`), or delete it if `test_pool_engine.py` already covers "clearing pays out of others' entries" (check first, prefer delete if covered).
- [ ] **Step 4:** `git rm scripts/seed_demo.py`, delete the `seed` target from `Makefile`, and fix any doc that mentions `make seed`.

### Task 3.4: Remove game selection

- [ ] **Step 1:** `models/user.py`: delete `active_games` (and its docstring). Keep `dismissed_checklists` only if the chess onboarding checklist stays (Task 6).
- [ ] **Step 2:** `routers/me.py` + `schemas/`: delete the active-games endpoints/fields. `grep -rn active_games apps/api/src` → zero hits.
- [ ] **Step 3:** Delete `apps/api/tests/test_active_games_retention.py`. Update `test_dismissed_checklists.py` and `test_getting_started.py` to chess-only.

### Task 3.5: Rewrite the shared tests that used other games as fixtures

These test kept code but used CS2/PUBG/Dota as sample data: `conftest.py`, `factories.py`, `golden/bar_snapshots.json`, `test_adapter_registry.py`, `test_admin_contests.py`, `test_admin_ops_views.py`, `test_aggregate_metrics.py`, `test_analytics.py`, `test_bar_direction.py`, `test_bar_golden.py`, `test_bar_realism.py`, `test_bootstrap_preserves_prior.py`, `test_challenge_service.py`, `test_challenges_endpoints.py`, `test_chaos_resilience.py`, `test_chat.py`, `test_contested_games.py`, `test_disputes.py`, `test_docs_do_not_drift.py`, `test_game_stats_service.py`, `test_grading_endpoint.py`, `test_host_clients.py`, `test_linking_models.py`, `test_links_endpoints.py`, `test_live_activity.py`, `test_markets.py`, `test_match_lifecycle.py`, `test_matchmaking.py`, `test_metric_models_service.py`, `test_migration_seed_parity.py`, `test_nightly.py`, `test_no_secret_endpoints.py`, `test_play_endpoints.py`, `test_pool_engine.py`, `test_pools_tournaments_endpoints.py`, `test_production_config.py`, `test_risk_detectors.py`, `test_sandbagging.py`, `test_secret_logging.py`, `test_settlement_worker.py`, `test_tournament_engine.py`, `test_win_required_metric.py`, `test_worker_contests.py`.

Rules:
- [ ] **Step 1:** A test whose *subject* is a non-chess behaviour (stat races, `win_next`, Steam ban checks, PUBG rate limits) → delete the test function (it was preserved in `future-expansion/` via Task 2.2 where relevant).
- [ ] **Step 2:** A test whose subject is generic (ledger, escrow, settlement, pools, disputes, chat) but whose fixture used another game → switch the fixture to `GAME_CHESS_LICHESS` and, for metric-based pools, `chess_moves`. Do not weaken assertions. Every money assertion (`sum(payouts) + rake == sum(entries)`, no rake on refund) must still run.
- [ ] **Step 3:** `golden/bar_snapshots.json`: drop non-chess keys; do not regenerate chess values (a changed chess value means a behaviour change, which is a bug here).
- [ ] **Step 4:** Run `make test-api`. Target: everything green except baseline pre-existing failures. Then:

```bash
cd apps/api && uv run ruff check . && uv run mypy src
grep -rn -i -E "cs2|pubg|dota|opendota|steam|sharecode|demo_mode|test_opponents|simulated" src tests
```
Expected: no hits except the word "simulated" in unrelated prose, if any.

- [ ] **Step 5:** Commit: `git commit -am "refactor(api): chess-only — remove CS2, demo scaffolding, multi-game plumbing"`

---

## Phase 4 — Database migration

### Task 4.1: Squash migrations into one baseline

The prod DB is gone, so 28 incremental migrations (many CS2/game-selection churn) collapse into one file generated from the chess-only models.

**Files:**
- Delete: `apps/api/migrations/versions/*.py`
- Create: `apps/api/migrations/versions/0001_baseline.py`
- Modify/Delete: `apps/api/tests/test_migration_seed_parity.py`

- [ ] **Step 1:** Before deleting, collect every **data** operation in the old migrations (seed rows such as `feature_flags` defaults, `metric_models` priors, limits). `grep -n -E "op\.(execute|bulk_insert)" apps/api/migrations/versions/*.py`. Keep only chess-relevant seeds.
- [ ] **Step 2:** Delete the old files and autogenerate against an empty DB.

```bash
cd apps/api
git rm migrations/versions/*.py
dropdb -h localhost -p 5544 -U moneymatch moneymatch && createdb -h localhost -p 5544 -U moneymatch moneymatch
uv run alembic revision --autogenerate --rev-id 0001 -m baseline
```

- [ ] **Step 3:** Review the generated file by hand: check constraints, partial indexes, `server_default`s and enum types that autogenerate misses (compare against the models). Append the seed `op.execute`/`bulk_insert` calls from Step 1. `downgrade()` drops everything.
- [ ] **Step 4:** Verify the models and the migration agree: `uv run alembic upgrade head && uv run alembic check` → "No new upgrade operations detected."
- [ ] **Step 5:** `test_migration_seed_parity.py`: keep if it still guards seed-vs-constants parity for chess; otherwise delete. Run `make test-api`.
- [ ] **Step 6:** Commit: `feat(db): squash migrations into a chess-only baseline`

---

## Phase 5 — Frontend: chess only

### Task 5.1: Delete non-chess and demo UI

- [ ] **Step 1:** Delete.

```bash
W=apps/web/src
git rm -r $W/components/cs2
git rm $W/hooks/useCs2.ts $W/lib/steamReturn.ts $W/lib/steamReturn.test.ts $W/pages/SteamCallbackPage.tsx \
  $W/components/DemoHandles.tsx $W/components/DemoHandles.test.tsx \
  $W/pages/DemoSignInPage.tsx $W/pages/DemoSignInPage.test.tsx $W/lib/demoAuth.ts \
  $W/components/GameSelectOverlay.tsx $W/components/GameSelectOverlay.test.tsx \
  $W/hooks/useGameSelection.ts $W/hooks/useGameSelection.test.ts
```

- [ ] **Step 2:** `App.tsx`: remove the `/demosignin` and `auth/steam/callback` routes and imports.
- [ ] **Step 3:** `SignInPage.tsx` (726 lines): remove the demo-login entry point. While there, note anything bloated for the UI pass (Task 6).

### Task 5.2: Collapse the game registry to chess

- [ ] **Step 1:** `lib/games.tsx`: keep the registry *shape* (one entry, chess) so adding a title later is one entry. Delete the beta-gating helper and its `TODO(beta-invite)`.
- [ ] **Step 2:** Update every file the earlier grep listed: `ChallengeDialog.tsx`, `chat/InviteCard.tsx`, `chat/InviteSheet.tsx`, `GameChecklists.tsx`, `LinkGames.tsx`, `rail/SideRail.tsx`, `ui/GameBadge.tsx`, `hooks/useLinks.ts`, `hooks/usePools.ts`, `hooks/useTournaments.ts`, `hooks/useSettlementCelebration.ts`, `lib/labels.ts`, `pages/ProfilePage.tsx`, `pages/admin/AdminContestsPage.tsx`, and their tests. Remove game pickers/tabs where only one option remains (`GameTabs`, game filters in `FilterBar`); a one-option selector is UI noise.
- [ ] **Step 3:** `GameChecklists.tsx` → a single chess onboarding checklist (link Lichess → play first match). Rename to `GettingStarted.tsx` if that reads better at call sites.

### Task 5.3: Regenerate the API client and get green

- [ ] **Step 1:** Start the API (`make api`), then `pnpm gen:api`. Commit the regenerated `packages/api-client/src/generated/schema.ts` and `openapi.json`.
- [ ] **Step 2:** `pnpm typecheck && pnpm lint && pnpm test`. Fix every type error the regenerated schema reveals (that's the point of regenerating).
- [ ] **Step 3:** `grep -rn -i -E "cs2|pubg|dota|steam|demo" apps/web/src` → only play-money wallet copy and e2e seam hits remain.
- [ ] **Step 4:** Commit: `refactor(web): chess-only — remove CS2, Steam, demo login and game selection`

---

## Phase 6 — UI/UX polish pass

The design system (`docs/design-guidelines.md`, tokens in `apps/web/src/styles/index.css`) is solid; the job is consistency, focus and finish, not a new look. Use the `frontend-design` skill for this phase. Constraints from PRODUCT_CONTEXT §12: real numbers or none, the fee shown before every commit, no "win big" tone.

### Task 6.1: Audit with screenshots

- [ ] **Step 1:** Run the stack locally with the e2e auth seam and a seeded chess user. Use Playwright to screenshot every route at 390px and 1440px: `/signin`, `/i/:token`, `/play` (idle, searching, matched, in-game, settled win/loss/draw), `/pools`, `/tournament`, `/activity`, `/social` (friends, chat, inbox), `/wallet`, `/profile`, `/admin/*`.
- [ ] **Step 2:** Write an audit table in this plan (screen × issue × fix). Check against: one primary action per screen; hierarchy (the money number and the next step are the first two things you see); empty/loading/error states on every query; skeletons instead of spinners; copy is plain and short; the fee is visible pre-commit; no invented numbers (check `Ticker`, `LiveLine`, live activity); touch targets ≥ 44px; focus rings; `prefers-reduced-motion` honoured by `SettlementCelebration` and `AnimatedBalance`; contrast per the token table.
- [ ] **Step 3:** Review the audit with the user before implementing. The audit lists the fixes; this plan does not invent them before the screens have been looked at.

### Task 6.2: Implement the audit fixes, screen by screen

- [ ] One commit per screen. Each commit: component change + updated/added vitest test for any behaviour change + before/after screenshot pair attached to the PR.
- [ ] Chess-specific finish worth doing now that it's the hero title: show the Lichess time control and rating band on the match slip and versus card, deep-link "Open game on Lichess" when the game is created, and show a live board state if `live_match` data is already available (it is: `ChessLichessAdapter.live_match`).
- [ ] Update `docs/design-guidelines.md` for any new or changed primitive in the same commit.

---

## Phase 7 — Deployment

### Task 7.1: Run the worker as its own service

- [ ] **Step 1:** Rewrite `render.yaml` as a working Blueprint that describes exactly what runs, with short comments only:
  - `databases: moneymatch-postgres`, `plan: basic-256mb`, `postgresMajorVersion: "16"`. (Paid tier: free Render Postgres is deleted after 30 days, which is what lost the old DB.)
  - `moneymatch-api`: `type: web`, `runtime: docker`, `plan: starter`, `healthCheckPath: /api/v1/health`, `DATABASE_URL` from the DB, `fromGroup: moneymatch-shared`.
  - `moneymatch-worker`: `type: worker`, `runtime: docker`, `plan: starter`, `dockerCommand: python -m moneymatch_api.workers.settlement_worker`, same DB + env group.
  - Same `region:` on all three (pick the one closest to the Supabase project's region).
  - `envVarGroups: moneymatch-shared` declaring every secret as `sync: false`: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or JWKS settings, whichever `auth.py` uses), `WEB_ORIGIN`, `SENTRY_DSN`, `POSTHOG_API_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`. Derive the exact list from the final `config.py`; `ENV=prod` is a plain value.
  - Delete the `moneymatch-gc` pserv, the commented worker block, and all incident-history comments.
  - The DB URL format: `config.py` expects `postgresql+asyncpg://`. Check whether it rewrites Render's `postgres://` connection string; if not, add that normalization (one line, with a test).
- [ ] **Step 2:** `make dev` already runs the worker as its own process, so delete `run_worker_in_process` from `config.py` and the in-process path from the `main.py` lifespan. One way to run the worker, not two.
- [ ] **Step 3:** `docker-entrypoint.sh`: keep `alembic upgrade head` for the API only. The worker must not race it. Have the worker's `dockerCommand` bypass migration (`ENTRYPOINT` + `CMD` split, or a `MIGRATE=0` env check). Trim the comment to two lines.
- [ ] **Step 4:** Delete `apps/worker/` (dead shim) and update `docker-compose.yml`'s `full` profile to include a `worker` service.
- [ ] **Step 5:** `apps/web/vercel.json`: the CSP `connect-src` hardcodes `https://moneymatch.onrender.com`. Replace it with `https://api.dueloro.com` (keep the onrender origin too until the custom domain is verified, then remove it). Without this, the web app is blocked from calling a new API host.
- [ ] **Step 6:** Commit: `chore(deploy): blueprint with separate worker, paid DB; drop sidecar`

---

## Phase 8 — Documentation

### Task 8.1: Move business/legal docs to `docs-export/`

- [ ] **Step 1:** Move (user exports these, then a later commit deletes the folder):

```bash
mkdir -p docs-export
git mv docs/legal/legal-compliance.md docs/legal/integrity-audit.md \
  docs/business/unit-economics.md docs/business/business-and-competition.md \
  docs/business/website-recommendations.md docs/brand-and-name.md docs-export/
```
Rationale: legal memo + integrity audit are a counsel brief; unit economics and competition are pitch material; website recommendations are for the marketing site; brand guide is useful to marketing. All are stale on the PoC/"gems" model, so they don't belong in an engineering repo either way.

- [ ] **Step 2:** Delete stale ones outright: `docs/business/gtm-prelaunch.md`, `docs/product/overview.md`, `docs/product/roadmap.md` (both superseded by `PRODUCT_CONTEXT.md`), `docs/research/` (bar math across four games).

### Task 8.2: Write the slim doc set

Target: `docs/` holds 6 files, each short.

- [ ] `docs/README.md`: an index of the 6 docs, one line each.
- [ ] `docs/PRODUCT_CONTEXT.md`: unchanged (source of truth).
- [ ] `docs/architecture.md`: merges what's still true from `decisions.md`, `data-model.md`, `agent-handoff.md`, `implementation-guide/implementation-summary.md`. Covers: system diagram, the 6 invariants with where each is enforced (file:function), the money path, the adapter seam, the three play models, and the data model table list. Target ≤ 300 lines.
- [ ] `docs/development.md`: merges `DEVELOPMENT.md`, `CONTRIBUTING.md`, testing bits of `game/testing-chess.md` and `game/chess.md`. Covers local setup (db on :5544, test db on :5433), make targets, testing a real Lichess match locally, branch/commit/PR rules.
- [ ] `docs/runbook.md`: trimmed to deploy, migrate, rollback, worker health, reconciliation, incident steps. Absorbs `email-auth-setup.md`.
- [ ] `docs/design-guidelines.md`: kept and updated in Phase 6.
- [ ] Root `README.md`: cut to pitch paragraph + quickstart + link to `docs/README.md`. Remove "Chess, CS2, Dota 2, PUBG" and "FACEIT".

### Task 8.3: Delete the rest

- [ ] **Step 1:**

```bash
git rm -r docs/fixes docs/superpowers docs/implementation-guide docs/game docs/business docs/legal docs/product
git rm docs/decisions.md docs/data-model.md docs/agent-handoff.md docs/audit-2026-08-24.md docs/email-auth-setup.md
git rm DEVELOPMENT.md CONTRIBUTING.md
git mv docs/email-templates supabase/email-templates
```

- [ ] **Step 2:** Fix every link: `grep -rn -E "docs/(fixes|superpowers|implementation-guide|game|decisions|data-model|agent-handoff|adding-a-)" --include='*.md' --include='*.py' --include='*.ts*' .` → zero hits (code comments citing "08-phase-5 §3"-style doc sections should be shortened to plain explanations where they're now dangling).
- [ ] **Step 3:** Update `test_docs_do_not_drift.py` for removed constants (or delete it if Task 8.4 removes the docstrings it guards).
- [ ] **Step 4:** Commit: `docs: cut to six chess-only docs; business/legal staged in docs-export/`

### Task 8.4: Comment and docstring diet (whole repo)

Baseline (2026-11-06): `apps/api/src` has ~1,550 `#` comment lines + ~3,150 docstring lines in 26k lines; `apps/web/src` has ~1,850 comment lines in 20k lines; 217 citations of planning docs (`08-phase-5 §3`, `01-architecture §2`, …) that no longer exist. Target: cut comment/docstring volume by at least half.

**Rules (brevity first; not all code needs explaining):**
- Delete comments that restate the code, narrate history ("this is what stranded beta at 0010…"), cite deleted docs (`NN-phase-N`, `§N`, `design PDF p.1`), or argue with a past reviewer. History lives in git.
- Module docstrings: 1–3 lines saying what the module is for. Function docstrings only where the name + signature don't make the contract obvious.
- **Keep** short *why* comments where the code would otherwise look wrong or a change could break money: invariant enforcement, `FOR UPDATE SKIP LOCKED`, integer-cent rounding, idempotency guards, security checks. One or two lines each.
- No behaviour changes. Comments and docstrings only. Don't reformat code.

- [ ] **Step 1:** Do it one directory per commit, so each diff is reviewable: `apps/api/src/moneymatch_api/{services,routers,workers,models,adapters,(top-level)}`, then `apps/web/src/{components,pages,hooks,lib}`, then `apps/api/tests` (test docstrings → one line or none), then config files (`render.yaml`, `docker-compose.yml`, `Makefile`, `docker-entrypoint.sh`, `pyproject.toml`).
- [ ] **Step 2:** After each commit: `make test` (catches broken doctests or doc-drift tests) and `git diff --stat` to confirm only comment lines changed. A quick filter: `git diff -U0 | grep -E '^[+-]' | grep -v -E '^[+-]\s*(#|//|\*|/\*|"""|$)'` should show only docstring body lines.
- [ ] **Step 3:** Re-measure with the same commands as the baseline and record the numbers here. `grep -rhoE "[0-9]{2}-phase-[0-9]|§ ?[0-9.]+" apps/` → 0.

---

**Applies to every phase, not just 8.4:** any new code written in this plan (migration, README, render.yaml, UI changes) follows the same brevity rules from the start.

## Phase 9 — End-to-end verification

### Task 9.1: Prove the product works

- [ ] **Step 1:** `make test` green; `pnpm typecheck && pnpm lint`; `uv run mypy src`.
- [ ] **Step 2:** Local, real Lichess, two accounts (two browsers): link Lichess → queue H2H in the same band → game is created on Lichess → play it → settlement in < 1 min → both ledgers correct, fee = 10% of pot, `GET /admin/reconciliation` clean. Repeat for a draw (push, no fee).
- [ ] **Step 3:** Solo pool: join a chess pool, win a game under your bar, confirm payout math. Tournament: same.
- [ ] **Step 4:** Social: friend request → challenge → accept → rematch; invite link from a signed-out browser; chat; push notification; file a dispute and resolve it in admin.
- [ ] **Step 5:** After the Render setup below, repeat Step 2 against `api.dueloro.com` from the Vercel beta.

---

## Manual steps for the user (outside the codebase)

**Render: rebuild from scratch on the personal account** (do this after Phase 7 is merged, since the Blueprint reads `render.yaml` from the repo)

Cost: API Starter (~$7) + Worker Starter (~$7) + Postgres basic-256mb (~$6) ≈ $20/mo, so the $50 credit covers ~2.5 months. Check the credit's expiry date in Billing. Confirm current prices on the dashboard before creating anything.

1. [ ] **Old account:** delete the old `moneymatch` web service (and `moneymatch-gc` / any leftover worker). Its DB is already gone. This frees the old service and may free the `moneymatch` subdomain; Render doesn't guarantee reuse, which is why we also use `api.dueloro.com`.
2. [ ] **GitHub access:** in the personal Render account, Account Settings → Git → connect GitHub, and grant the Render app access to `Dueloro/moneymatch`. If Dueloro is an org, an org owner may need to approve the app.
3. [ ] **Create from Blueprint:** Dashboard → New → Blueprint → pick `Dueloro/moneymatch`, branch `main`. Render reads `render.yaml` and shows the DB, API, worker and the `moneymatch-shared` env group. Name the API service `moneymatch` if you want to try for `moneymatch.onrender.com`.
4. [ ] **Fill in secrets** when prompted (or under Env Groups → `moneymatch-shared`). Get them from the old account's env group before deleting it if you can still see it, otherwise from each provider:
   - Supabase: Project Settings → API (URL, JWT secret / JWKS).
   - `WEB_ORIGIN`: the Vercel production URL of the web app (exact origin, no trailing slash).
   - Sentry DSN, PostHog project key, Resend API key + `EMAIL_FROM`, VAPID keys (reuse the old ones; regenerating them breaks existing push subscriptions, which are gone anyway with the DB, so new ones are fine too).
5. [ ] **Apply.** Watch the API deploy log: the entrypoint runs `alembic upgrade head` (one baseline migration), then uvicorn starts. The worker log should show cycle heartbeats. `curl https://<api-host>/api/v1/health` → 200.
6. [ ] **Custom domain:** API service → Settings → Custom Domains → add `api.dueloro.com`. At the dueloro.com DNS provider, add the CNAME Render shows. Wait for the certificate to show "Verified".
7. [ ] **Admin:** sign in once on the web app, then `scripts/grant_admin.py` against the new DB (Render Shell on the API service, or locally with the DB's external URL) to make yourself admin.

**Later, moving to a corporate Render account:** repeat steps 2–6 in the new workspace, `pg_dump` the old DB → `pg_restore` into the new one with the worker stopped, repoint the `api.dueloro.com` CNAME, then delete the personal services. The frontend doesn't change because it only knows `api.dueloro.com`.

**Steam / PUBG / Valve**
- [ ] Revoke the Steam Web API key and the PUBG developer API key. Sign out / revoke the refresh token of the sidecar's dedicated Steam account.

**Vercel**
- [ ] Set `VITE_API_BASE_URL=https://api.dueloro.com` (Production + Preview), then redeploy. Env vars are baked in at build time.
- [ ] Make sure `VITE_E2E_AUTH` is unset or `false` in prod. Confirm the project still deploys from `Dueloro/moneymatch:main`.

**Supabase**
- [ ] Remove the Steam callback URL (`/auth/steam/callback`) from Auth → URL Configuration → Redirect URLs. Update email templates from `supabase/email-templates/` if Phase 6 touched copy. Delete the `demo@dueloro.com` auth user if one exists.

**PostHog**
- [ ] Archive or relabel insights/dashboards built on CS2/PUBG/Dota or game-selection events. Remove any per-game feature flags. Annotate the deploy date ("chess-only").

**Sentry**
- [ ] Resolve CS2/sidecar/Steam issues as "resolved in next release". Mute alerts tied to the sidecar health check.

**Resend**
- [ ] Nothing structural. Check any transactional email copy mentions only chess.

**Lichess**
- [ ] Nothing, unless the Lichess token used for brokered games is about to expire. Check its scopes and expiry while you're at it.

**Players**
- [ ] Existing beta players keep their Supabase logins; their app profile, Lichess link and play-money balance were in the deleted DB. Tell them (Discord/email via Resend) to sign in and relink Lichess. Their account is recreated automatically on sign-in.

**After deploy**
- [ ] Export `docs-export/`, then delete it in a follow-up commit.
- [ ] Update memory: the CS2 sidecar notes and "project current state" no longer apply.

---

## Baseline

2026-11-06 at tag `pre-chess-only`: API 1210 passed; web 40 files / 222 tests passed; web typecheck + lint clean. No pre-existing failures.

Local env notes: run API tests as `cd apps/api && SUPABASE_URL=https://example.supabase.co uv run pytest -q` (repo `.env` can't be shell-sourced: line 72 `EMAIL_FROM` is unquoted). Test DB container `mm-test-db` on :5433, dev DB `moneymatch-db-1` on :5544.

