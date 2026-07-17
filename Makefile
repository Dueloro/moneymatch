# MoneyMatch dev commands. `make dev` brings the whole stack up locally.
# Env comes from the repo-root .env (copy .env.example → .env first).
.DEFAULT_GOAL := help
.PHONY: help install db down migrate api web dev test test-api test-web \
        lint typecheck gen-api seed worker e2e

# Source the repo-root .env into a recipe (api/migrate need DATABASE_URL etc).
# $(CURDIR) anchors to the Makefile dir so it works after `cd apps/api`.
LOADENV := set -a; [ -f $(CURDIR)/.env ] && . $(CURDIR)/.env; set +a;

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install all deps (pnpm workspace + api venv)
	pnpm install
	cd apps/api && uv sync --extra dev

db: ## Start Postgres (Docker) and wait until healthy
	@$(LOADENV) docker compose up -d db
	@echo "waiting for postgres..."
	@until docker compose exec -T db pg_isready -U moneymatch >/dev/null 2>&1; do sleep 1; done
	@echo "postgres ready"

down: ## Stop all Docker services
	@$(LOADENV) docker compose down

migrate: ## Apply DB migrations
	cd apps/api && $(LOADENV) uv run alembic upgrade head

api: ## Run the API (reload) on :8000
	cd apps/api && uv run uvicorn moneymatch_api.main:app --reload --port 8000 --env-file ../../.env

web: ## Run the web app (Vite) on :5173
	cd apps/web && pnpm dev

worker: ## Run the settlement worker (polls Postgres; separate process)
	cd apps/api && uv run --env-file ../../.env python -m moneymatch_api.workers.settlement_worker

dev: db migrate ## Start db + api + worker + web together
	@echo "starting api + worker + web (Ctrl-C to stop)..."
	@$(MAKE) -j3 api worker web

test: test-api test-web ## Run all tests

test-api: ## Run API tests (needs Postgres up)
	cd apps/api && $(LOADENV) uv run pytest

test-web: ## Run web tests
	pnpm --filter @moneymatch/web test

e2e: ## Run the Playwright H2H e2e (needs the stack up — see apps/web/e2e/README.md)
	pnpm --filter @moneymatch/web exec playwright install --with-deps chromium
	pnpm --filter @moneymatch/web test:e2e

seed: ## Seed a demoable environment (users, tickets, a pool, a tournament)
	cd apps/api && $(LOADENV) uv run python ../../scripts/seed_demo.py

lint: ## Lint everything
	cd apps/api && uv run ruff check src tests ../../scripts \
		&& uv run ruff format --check src tests ../../scripts
	pnpm --filter @moneymatch/web lint
	pnpm exec prettier --check "**/*.{ts,tsx,css,json,md}"

typecheck: ## Typecheck api (mypy) and web (tsc)
	cd apps/api && uv run mypy src
	pnpm --filter @moneymatch/web typecheck

gen-api: ## Regenerate the TS API client from the running API
	pnpm gen:api
