# Database state — snapshot of the local environment

Read-only snapshot taken **2026-08-08** from the local Docker Postgres
(`localhost:5432/moneymatch`). Emails and host ids are redacted; everything else
is verbatim.

Schema version: **`0017_chat`** (the chat tables are the latest migration).

This is a point-in-time picture, not a schema reference. To regenerate it, see
§7.

---

## 1. The one-paragraph summary

There are **11 users**, none of which is a real signup: 5 from `make seed`
(`admin`, `player1`..`player4`), 5 demo opponents seeded by demo login, and the
shared `demo` account. **You have been testing as `demo`**, and that account has
your real Lichess handle **`lifeunicorn`** bound to it.

The database has plenty of history from earlier seeded runs: 23 solo pools, 8
tournaments, 6 matches, and 198 ledger entries. Almost all of the contests are
`CANCELED` (they never reached the minimum field), which is expected when there
is only one real player.

---

## 2. Row counts, every table

| Table | Rows | |
| --- | --- | --- |
| `users` | 11 | 5 seed, 5 demo opponents, 1 demo |
| `wallets` | 11 | one per user |
| `limits` | 11 | one per user |
| `linked_accounts` | 26 | seed users are linked to all 4 games |
| `metric_models` | 61 | per user × game × metric |
| `ledger_entries` | 198 | the money trail |
| `platform_ledger` | 32 | rake |
| `queue_tickets` | 33 | |
| `solo_pools` | 23 | |
| `solo_entries` | 39 | |
| `tournaments` | 8 | |
| `tournament_entries` | 32 | |
| `matches` | 6 | |
| `match_players` | 12 | |
| `notifications` | 91 | |
| `messages` | 30 | chat |
| `conversations` | 4 | |
| `conversation_members` | 7 | |
| `friendships` | 3 | |
| `live_snapshots` | 16 | cached host reads |
| `raw_payloads` | 29 | settlement evidence |
| `feature_flags` | 8 | |
| `admin_audit` | 0 | nobody has been granted admin |
| `disputes` | 0 | |
| `risk_flags` | 0 | |
| `push_subscriptions` | 0 | |

---

## 3. Users

| `auth_id` | `username` | `role` | Origin |
| --- | --- | --- | --- |
| `seed_admin` | `admin` | **admin** | `make seed` |
| `seed_player1` … `seed_player4` | `player1` … `player4` | user | `make seed` |
| `demo_opp_*` | `Rojo`, `shroud_btw`, `s1mple_fan`, `chocoTaco`, `kvem_` | user | demo login fixture |
| `demo-user` | `demo` | user | demo login |

**`admin_audit` is empty and `seed_admin` already has `role = 'admin'`.** That
account was created with the role by the seed script rather than granted through
`grant_admin.py`, which is why there is no audit row.

No practice opponents (`zz_testbot_*`) exist yet, so no contest has been filled
from the demo account so far. They appear the first time `demo` joins one.

---

## 4. Chess links, and what they mean

| App user | Lichess handle | Status | `total_games` |
| --- | --- | --- | --- |
| `demo` | **`lifeunicorn`** | active | **2** |
| `demo` | `demo` | unbound | 120 |
| `player1`..`player4` | `player1`..`player4` | active | null |

Two things matter here.

**`lifeunicorn` is your real account and it resolves.** Its stored snapshot:

```jsonc
{
  "username": "lifeunicorn",
  "url": "https://lichess.org/@/lifeunicorn",
  "total_games": 2,
  "win_rate": 0.0,
  "account_age_days": 39,
  "primary_speed": "bullet",
  "formats": [
    { "speed": "bullet", "rating": 1123, "games": 2, "provisional": true }
  ]
}
```

That is a real fetch from `GET /api/user/lifeunicorn`. The rating (1123 bullet)
is what tournament fields form on.

**The seed players' chess links are fake.** Their host ids are `player1`..
`player4`, which are not real Lichess accounts, so polling them returns nothing.
They can enter a contest but can never be graded, so they are refunded. That is
harmless, and it is exactly what practice opponents do too.

---

## 5. Metric models

| Game | Metric | Rows | Mean µ |
| --- | --- | --- | --- |
| chess.lichess | `chess_accuracy` | 5 | 82.60 |
| chess.lichess | **`chess_moves`** | **1** | **15.48** |
| cs2.faceit | `cs2_kd_ratio` | 8 | 0.14 |
| cs2.faceit | `cs2_adr` | 8 | 9.75 |
| cs2.faceit | `cs2_headshot_pct` | 8 | 5.88 |
| dota2.opendota | `dota2_kda_ratio` | 5 | 0.64 |
| dota2.opendota | `dota2_gpm` | 5 | 104.00 |
| pubg.steam | `pubg_kills` | 7 | 0.64 |
| pubg.steam | `pubg_damage` | 7 | 54.29 |
| pubg.steam | `pubg_headshot_pct` | 7 | 3.14 |

**The single `chess_moves` row is yours**: µ 15.48, σ 0.5, n 2. It exists
because you pressed Refresh, and it is what makes Solo Pools show cards. Your
personal bars come out of it, so with σ 0.5 the three difficulties sit close
together (roughly 15.7 / 16.0 / 16.4 moves).

The 5 `chess_accuracy` rows are demo fixture leftovers. That metric has no live
data source and is no longer offered; the rows are inert.

---

## 6. Contests and money

**Solo pools (23).** Chess: 3 canceled easy, 2 settled medium (all on the dead
`chess_accuracy`). CS2: 9 canceled, 2 settled. Dota: 2 canceled, 2 settled.
PUBG: 1 canceled, 2 settled.

**Tournaments (8), all `CANCELED`**, two per game, all on the old rate metrics
(`chess_accuracy` for chess). None used the new aggregate metrics, because those
did not exist when these rows were written.

**Matches (6), all `SETTLED`**: 3 PUBG kills, 3 CS2 K/D. No chess match has ever
been played, which follows from chess being brokered and there being nobody to
broker with.

**Ledger (198 entries):**

| Type | Count | Net cents |
| --- | --- | --- |
| `demo_deposit` | 21 | +1,200,000 |
| `refund` | 71 | +78,500 |
| `payout` | 6 | +14,400 |
| `escrow_hold` | 83 | −94,500 |
| `escrow_release` | 12 | 0 |
| `demo_withdrawal` | 5 | −50,000 |

Refunds outnumber payouts 71 to 6, which is the signature of contests that
formed and then could not be graded. Expected with fake host accounts.

Balances: `demo` has $1,474.00 available and $0 in escrow; the seed players have
$1,000.00 each and nothing running.

---

## 7. Feature flags

| Key | Enabled |
| --- | --- |
| `game:chess.lichess` | true |
| `game:cs2.faceit` | true |
| `game:dota2.opendota` | true |
| `geo_config` | true |
| `nightly_last_run` | true |
| `queue_paused` | **false** |
| `settlement_paused` | **false** |
| `worker_heartbeat` | true |

Two things absent and worth noting:

- **`test_opponents` has no row, and no longer needs one.** Practice opponents
  are gated on the demo account rather than a flag (`services/demo_mode.py`).
  The admin flags page still merges declared defaults, which is worth keeping:
  a flag added in code used to be invisible until someone wrote a row, and
  nobody could write one.
- **`game:pubg.steam` has no row**, so PUBG runs on the code default (`True`).

---

## 8. Regenerating this snapshot

Read-only, safe to run any time. From the repo root, with the database up:

```bash
cd apps/api
DATABASE_URL="$(grep '^DATABASE_URL=' ../../.env | cut -d= -f2-)" \
  .venv/Scripts/python.exe -c "
import asyncio, os, asyncpg
URL = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://')
async def main():
    c = await asyncpg.connect(URL)
    for t in [r['tablename'] for r in await c.fetch(
        \"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename\")]:
        print(f'{t:24} {await c.fetchval(f\\\"SELECT count(*) FROM \\\\\\\"{t}\\\\\\\"\\\")}')
    await c.close()
asyncio.run(main())
"
```

Or just open a psql shell:

```bash
docker exec -it $(docker ps -qf name=postgres) psql -U moneymatch -d moneymatch
```

Useful one-liners once you are in:

```sql
\dt                                              -- list tables
SELECT username, role, status FROM users;
SELECT game, metric, mu, sigma, n FROM metric_models WHERE game = 'chess.lichess';
SELECT game, ranking_metric, state FROM tournaments ORDER BY created_at DESC;
SELECT entry_type, count(*), sum(amount_cents) FROM ledger_entries GROUP BY 1;
```

---

## 9. What this snapshot tells you about testing

1. **Your Lichess link works.** `lifeunicorn` resolved, and the stored snapshot
   carries a real bullet rating.
2. **Solo Pools should show cards**, because `chess_moves` has n = 2 and the
   threshold is 1.
3. **Tournaments were blocked by a bug, now fixed.** The markets endpoint marked
   every metric provisional unless a `MetricModel` existed, but the three
   aggregate chess metrics deliberately have none: they form fields on your
   Lichess rating instead. All three read as provisional, and the UI hides
   provisional metrics. The endpoint now uses the same rule the engine uses.
4. **Two rated games is thin.** Total wins and longest streak count only games
   inside the tournament window (48h by default), so expect small numbers, and a
   fastest-win contest needs at least one win in the window to score at all.
   Your stored `win_rate` is 0.0.
5. **`GAME_HISTORY_FLOOR` does not block you.** It is set to 20 for chess, but
   `meets_history_floor()` is defined and never called anywhere in the codebase,
   so it currently gates nothing.
