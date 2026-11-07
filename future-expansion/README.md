# Future expansion

Code and docs for titles we are not shipping yet. **Nothing in this folder is
imported, run, linted, or tested.** It is a reference snapshot taken at tag
`pre-chess-only` (commit `fa02ab7`, the last commit before the chess-only cut).

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
   this code is not maintained.

CS2 is intentionally absent. Its Game Coordinator sidecar approach was dropped.
If CS2 returns, start from the FACEIT Data API instead; the old code is at tag
`pre-chess-only`.
