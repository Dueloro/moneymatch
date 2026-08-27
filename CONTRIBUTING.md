# Contributing to Money Match

Money Match moves real money. The bar for a change is not "it works" but "it
cannot silently do the wrong thing with someone's balance." This document is the
one place for how we branch, commit, test, and review. For the deeper technical
map (invariants, the money path, what each test proves) read
[`docs/agent-handoff.md`](docs/agent-handoff.md).

## Repository shape

- `apps/api` — FastAPI backend (Python, `uv`). The money path lives here.
- `apps/web` — Vite/React frontend (`pnpm`).
- `gc-sidecar` — the CS2 Game Coordinator sidecar (Node).
- `docs/` — architecture, product, legal, and the agent handoff.
- `Makefile` — `make dev` brings the whole stack up. `make help` lists targets.

## Branch naming

`<type>/<short-kebab-summary>`, where `<type>` matches the commit types below:

```
feat/settlement-celebration
fix/pool-refund-rounding
docs/agent-handoff
chore/bump-uv-lock
```

Branch off `main`. Never commit directly to `main`.

## Commit messages — Conventional Commits

`<type>(<optional scope>): <summary>`

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`, `perf`,
`build`, `ci`. Keep the summary imperative and under ~72 chars.

```
fix(pool): an empty history must not overwrite a model
docs: record the NormGame / TelemetrySample contract
refactor: extract the twelve _now() copies into clock.now()
```

This is convention-only today; a `commitlint` config is available to enforce it
(see [Optional: commitlint](#optional-commitlint)).

## Before you open a PR — the checklist

Run the same gates CI runs. From `apps/api`:

- [ ] `uv run ruff check src tests` — lint clean
- [ ] `uv run ruff format --check src tests` — formatted
- [ ] `uv run mypy src` — types clean
- [ ] `uv run pytest` — full suite green (needs the test DB, see below)

From `apps/web`:

- [ ] `pnpm exec tsc --noEmit` — types clean
- [ ] `pnpm exec eslint . --max-warnings 0` — lint clean
- [ ] `pnpm exec prettier --check "**/*.{ts,tsx,css,json,md}"` — formatted
- [ ] `pnpm exec vitest run` — tests green

And always:

- [ ] New behavior has a test. New **money** behavior has a test that would fail
      if the amount were wrong (see the money-invariant tests in
      `docs/agent-handoff.md`).
- [ ] No floats anywhere on the money path — integer cents only.
- [ ] Touched a config var? Update `.env.example` **and** its required-vs-optional
      annotation.
- [ ] Touched a documented invariant or seam? Update the doc in the same PR.

## Testing

The full API suite is comprehensive (~12 minutes) and needs a Postgres. Fast
recipes for the inner loop are in [Fast-test recipes](#fast-test-recipes) below.

### The test database

API tests build the schema by running the Alembic migrations against a
throwaway Postgres, **separate from the dev DB**. Point them at it with
`TEST_DATABASE_URL` (default: `postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test`).
Bring one up before running DB-backed tests, e.g.:

```bash
docker run --rm -d --name mm-test-db -p 5433:5432 \
  -e POSTGRES_USER=moneymatch -e POSTGRES_PASSWORD=moneymatch \
  -e POSTGRES_DB=moneymatch_test postgres:16
```

### Fast-test recipes

The full run is the pre-PR gate, not the inner loop. While iterating:

```bash
# Pure-function tests only — NO database, sub-second. The `nodb` marker tags
# every test that touches only math/pure logic (money math, fairness, grading
# arithmetic, bar placement). This is the fastest signal.
uv run pytest -m nodb

# One file, or one test.
uv run pytest tests/test_pool_engine.py -q
uv run pytest tests/test_pool_engine.py::test_clearing_splits_the_pot -q

# By keyword across the suite.
uv run pytest -k "refund or reconcil" -q

# Re-run only what failed last time, stop on first failure.
uv run pytest --lf -x -q
```

Run the **full** `uv run pytest` before pushing — the fast recipes are for speed,
not for skipping coverage.

## Code review expectations

- **Correctness before style.** A reviewer's first job is to find where the
  change could move the wrong amount, skip an escrow, double-settle, or leak a
  test/demo path into production. Style nits come after.
- **Invariants are non-negotiable.** If a change touches anything in the
  "Invariants that must never break" list in `docs/agent-handoff.md`, the PR
  must show the test that still proves it.
- **Fail closed.** New failure modes on the money path should stop and refund or
  halt, never guess. Match the existing patterns (`ReconciliationError` halt,
  unverifiable → refund).
- **Keep the core game-agnostic.** New game-specific logic belongs behind the
  `GameAdapter` interface, not in the engines or the worker. The one documented
  exception (`_sync_share_chains`) is called out in the handoff doc.
- **Small, reviewable PRs.** Prefer a focused diff with a clear before/after over
  a sweeping one. Refactors land separately from behavior changes.

## Optional: commitlint

To enforce Conventional Commits locally, install commitlint and enable the hook:

```bash
pnpm add -D @commitlint/cli @commitlint/config-conventional
# then wire a commit-msg hook (husky or a native .git/hooks/commit-msg) that runs:
#   pnpm exec commitlint --edit "$1"
```

A ready `commitlint.config.js` lives at the repo root. Wiring the git hook is
opt-in so a fresh clone is never blocked from committing.
