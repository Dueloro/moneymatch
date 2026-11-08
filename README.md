# Money Match

Skill-based wagering on the competitive games you already play, settled
automatically by the game's API. A player picks a stake, gets matched with
someone in their skill band, plays on the real game (chess on Lichess today),
and the result settles from the game's official API in under a minute. No
screenshots, no reviewers, no waiting. Play money only for now.

_Money Match is developed by Dueloro, Inc._

## Quickstart

Needs Docker, Node 20+ with pnpm, and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env   # fill in the Supabase keys
make install && make dev
```

Open http://localhost:5173. Details in [`docs/development.md`](./docs/development.md).

## Repo layout

```
apps/api            FastAPI service + settlement worker (Python)
apps/web            React + Vite SPA (talks only to the API)
packages/api-client TypeScript client generated from the API's OpenAPI schema
future-expansion/   Parked code for other titles (not built or tested)
docs/               Product context, architecture, development, runbook, design
```

Start with [`docs/README.md`](./docs/README.md).
