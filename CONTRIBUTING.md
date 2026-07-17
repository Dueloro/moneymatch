# Contributing to MoneyMatch

Engineering standards live in
[`docs/implementation-guide/00-README.md`](./docs/implementation-guide/00-README.md) §3.
This file is the operational summary. Read §3 before your first PR — those
invariants are non-negotiable and enforced in review.

## Non-negotiable invariants

1. **The server owns every number.** No client-supplied amounts, timestamps,
   telemetry, or results. Clients send intents with ids.
2. **Append-only ledger.** Every wallet mutation is a `ledger_entries` row;
   balances are a transactionally-maintained cache.
3. **Money is integer cents** (`BIGINT`), never floats.
4. `sum(payouts) + rake == sum(entries)` on every settlement path; refunds and
   pushes rake nothing.
5. **Settlements are host-API-verified** through adapters; no self-reporting.
6. **No odds/lines** — on-screen multipliers are derived pot math.

## Git workflow (trunk-based)

- Short-lived branches off `main`, named `phase-N-...` or `feat/...`.
- **Conventional-commit subjects**, no co-author trailers:
  `feat:`, `fix:`, `chore:`, `test:`, `docs:`, `ci:`, `refactor:`.
- Small, frequent commits. Open a PR, get CI green, **squash-merge** to `main`.
- Every schema change ships with its Alembic migration in the same PR
  (migrations are forward-only).
- No secrets in the repo. `.env.example` documents every variable; `config.py`
  fails fast on a missing one.

### Branch protection (configure on GitHub once the repo is remote)

- Require the `api` and `web` CI jobs to pass before merge.
- Require branches to be up to date with `main`.
- Disallow direct pushes to `main`; require a PR.

## Local setup

See [`README.md`](./README.md) for the from-clone run steps. In short:

```bash
cp .env.example .env          # fill in Supabase keys
corepack enable pnpm          # if pnpm isn't installed
pnpm install
make dev                      # postgres + api + web
```

Install pre-commit hooks (mirrors CI gates):

```bash
pipx install pre-commit   # or: uv tool install pre-commit
pre-commit install
```

## Tests gate merges

CI runs on every PR:

- **api**: `ruff`, `mypy`, `pytest`
- **web**: `eslint`, `prettier --check`, `tsc --noEmit`, `vitest`, `build`

Money-math and settlement paths **require** tests. Port the PoC invariant
suites first — they are the spec. Run locally before pushing:

```bash
make test        # api + web
```
