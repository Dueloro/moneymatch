# Development

## Prerequisites

- Node 20+ and pnpm (`corepack enable pnpm`)
- [uv](https://docs.astral.sh/uv/) (Python 3.12 for the API)
- Docker (for Postgres)

## Setup and run

```bash
cp .env.example .env   # fill in SUPABASE_URL and the VITE_SUPABASE_* keys
make install           # pnpm workspace + API venv
make dev               # Postgres, migrations, then API + worker + web
```

- Web: http://localhost:5173. API: http://localhost:8000 (docs at `/docs`).
- `make help` lists every target. Pieces run alone with `make db`,
  `make migrate`, `make api`, `make worker`, `make web`.
- Every target reads the root `.env`. `config.py` fails fast on a missing
  required variable; `.env.example` documents them all.

### Dev database

`make db` starts Postgres 16 in Docker on host port `DB_PORT` (default 5432).
If 5432 is taken, use another port, e.g. `DB_PORT=5544`, and set the same port
in `DATABASE_URL`.

### Test database

API tests build their schema by running the migrations against a separate,
throwaway database at `TEST_DATABASE_URL` (default
`postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test`).
Start it once:

```bash
docker run -d --name mm-test-db -e POSTGRES_USER=moneymatch \
  -e POSTGRES_PASSWORD=moneymatch -e POSTGRES_DB=moneymatch_test \
  -p 5433:5432 postgres:16
```

After a reboot: `docker start mm-test-db`.

## Tests

```bash
make test           # API (pytest) + web (vitest)
pnpm test           # web only
cd apps/api && uv run pytest -m nodb      # pure-function tests, no DB, fast
cd apps/api && uv run pytest tests/test_pool_engine.py -q
cd apps/api && uv run pytest --lf -x -q   # rerun last failures
```

Run the full suite before pushing. Money and settlement changes need a test
that would fail if an amount were wrong.

Other checks CI runs: `make lint`, `make typecheck`.

## API client

The web app uses a TS client generated from the API's OpenAPI schema. After
changing a schema or route, with the API running:

```bash
pnpm gen:api
```

Never hand-write a duplicate API type in `apps/web`.

## Migrations

```bash
cd apps/api && uv run alembic revision --autogenerate -m "short description"
make migrate
cd apps/api && uv run alembic check   # must report no new operations
```

Forward-only. Ship the migration in the same PR as the model change.

## Testing a real Lichess match locally

Contests only form with real opponents, so you need two players.

1. `make dev` (the worker must be running; it does the grading).
2. Sign in as two different users in two browser profiles (one can be
   private/incognito).
3. Each user links a different Lichess account under Profile. Pick accounts
   within 800 rating points so they pair.
4. Both open Play → Head-to-head and queue the same speed and stake. Both
   confirm the match.
5. Both open the Lichess game link and play it out.
6. Within a worker cycle (15 s) the match settles. Check Activity and Wallet.

Pools need 3 players and tournaments 6, all linked and similar-rated; they
settle from rated games inside the window (24h pools, 48h tournaments; see
`POOL_WINDOW_SECONDS` / `TOURNAMENT_WINDOW_SECONDS` in `constants.py`).

To check what Lichess returns for an account (no key needed):

```bash
curl -s https://lichess.org/api/user/YOUR_USERNAME | jq
curl -s -H 'Accept: application/x-ndjson' \
  'https://lichess.org/api/games/user/YOUR_USERNAME?max=3&rated=true&moves=true'
```

## End-to-end tests

Playwright specs in `apps/web/e2e/`. They need the full stack and two real
Lichess accounts. See [`apps/web/e2e/README.md`](../apps/web/e2e/README.md).

## Branches, commits, PRs

- Branch off `main`: `<type>/<short-summary>`, e.g. `fix/pool-refund-rounding`.
  Never commit to `main` directly.
- Conventional Commits: `<type>(<scope>): <summary>`, imperative, under ~72
  chars. Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`,
  `perf`, `build`, `ci`. `commitlint.config.js` encodes this; the git hook is
  opt-in (`pnpm add -D @commitlint/cli @commitlint/config-conventional`, then a
  `commit-msg` hook running `pnpm exec commitlint --edit "$1"`).
- Optional pre-commit hooks mirror CI: `pre-commit install`.
- Open a PR, get CI green (`.github/workflows/ci.yml`), squash-merge.
- Review for correctness first: wrong amounts, skipped escrow, double
  settlement, dev paths reaching prod. Keep game-specific logic inside the
  adapter. New failure modes on the money path should refund or halt, never
  guess.
- No secrets in the repo. A new config variable goes in `.env.example` too.
