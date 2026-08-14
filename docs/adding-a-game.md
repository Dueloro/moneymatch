# Adding a New Game (GameAdapter guide)

The whole product is built to add a title **without touching** matchmaking,
escrow, settlement, or the UI shell. You do that by implementing one interface —
`GameAdapter` — and registering it. Everything shared sees normalized value types
(`NormGame`, `TelemetrySample`, `ProfileSnapshot`), never host-specific JSON.

> **Before you start — the legal gate.** A title only carries money if its
> publisher ToS permits it and its outcome is skill-predominant. Riot / Epic /
> Supercell titles are **excluded** ([`legal/legal-compliance.md`](./legal/legal-compliance.md)
> §2). A game with no server-fetchable per-match telemetry can do head-to-head but
> **not** solo pools (no self-report, ever). Confirm both before writing code.

## The interface

`apps/api/src/moneymatch_api/adapters/base.py` defines `GameAdapter`. The
identity/profile surface is required; brokering/grading seams are optional and
default to "not supported".

| Member | Required? | Purpose |
| --- | --- | --- |
| `id: str` | yes | Game id, e.g. `chess.lichess`, `cs2.steam` |
| `brokered: bool` | yes | `True` if the platform can create the match itself (e.g. a Lichess challenge); `False` if players coordinate on the host and we settle on the shared match found in their histories |
| `link_account(method, identifier) -> ProfileSnapshot` | yes | Verify a host account exists; return its skill profile |
| `fetch_profile(account_id) -> ProfileSnapshot` | yes | Re-fetch a linked account's profile (refresh / rating badge) |
| `poll_eligible_games(account_id, since_ms, filters) -> list[NormGame]` | yes | Finished, eligible games since a timestamp — the settlement/grading input |
| `create_match(speed, users) -> dict \| None` | brokered only | Broker a game restricted to the two players' handles |
| `match_winner(game_id, players) -> str \| None` | brokered only | Winner `player_id`, `""` for a draw, `None` while unfinished/unverifiable |
| `live_match(game_id, players) -> dict \| None` | optional | Best-effort mid-game snapshot for the Activity live view; `None` = nothing to show |

### The normalized types (what shared code sees)

- **`NormGame`** — a finished game reduced to `{id, speed, rated, created_at_ms,
  moves, won, drawn, metrics}`. `won` is `True`/`False` for the linked user or
  `None` if unknown/draw. `metrics` carries **rate** stats (K/D, ADR, KDA, …).
- **`TelemetrySample`** — `{game, metrics}` for solo/pool grading. **Rate metrics
  only** — never raw totals or self-report.
- **`ProfileSnapshot`** — the normalized profile (`schemas/profile.py`) rendered on
  Profile and used for skill bracketing.

## Steps

1. **Study a live adapter.** `chess_lichess.py` is the brokered reference (open
   challenge + winner verification, no API key). `cs2_steam.py` is the
   non-brokered, telemetry-bearing reference. Capture real host responses the way
   [`game/chess.md`](./game/chess.md) does before parsing.
2. **Write `adapters/<game>.py`** implementing `GameAdapter`. Set `id` and
   `brokered`. Parse host JSON into `ProfileSnapshot` / `NormGame` inside the
   adapter — no host JSON escapes it. Rate metrics only.
3. **Register it** in `adapters/registry.py`: add the instance to `_ADAPTERS`.
   Resolution is by id via `registry.get(id)`; never import an adapter directly
   elsewhere.
4. **Feature flag.** Every game is gated by a `game:<id>` flag read from
   `feature_flags`. Seed it in a migration; `is_enabled()` treats an absent key as
   enabled. Admin can disable a game without a deploy (hides it from linking, marks
   it BLOCKED on Profile).
5. **Metric models.** Decide the game's skill metric(s) and how `metric_models`
   bootstrap from `poll_eligible_games` history (personal-bar pools depend on
   μ/σ per metric). Mirror an existing adapter's bootstrap.
6. **Config / secrets.** Add any API key to `.env.example` and `config.py`
   (fail-fast). Lichess + OpenDota need no key; FACEIT + PUBG do — a missing key
   makes those adapters fail-soft with a host error, not a crash.
7. **Tests.** Add a pytest suite with `respx`-mocked host responses covering
   link, profile refresh, `poll_eligible_games` parsing, and (brokered)
   `match_winner` including the draw/unfinished cases. The settlement-invariant
   suites are the spec — a new game must not break them.
8. **Regenerate the client.** `make gen-api` so the web app sees the new game
   id/metadata. No hand-written types.

## What you do NOT touch

Matchmaking, the queue, escrow/rake, the settlement worker, the ledger, and the
UI primitives are game-agnostic. If adding a game tempts you to edit any of them,
the seam is in the wrong place — fix the adapter boundary instead. Per-game
calibration (rating tables, metric definitions) belongs in the adapter or its
metric-model bootstrap, not in shared code.
