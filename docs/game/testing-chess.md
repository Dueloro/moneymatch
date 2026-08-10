# Testing chess end to end, with only your own account

A walkthrough for exercising the real Lichess path (fetch → grade → settle) when
you are the only player in the system.

You do **not** need an admin account for this. The short version is one line in
`.env`. The admin route exists too, and is explained at the end for when you are
testing on a deployed environment where you cannot restart the API.

---

## Why anything special is needed

Nothing forms with one player. A solo pool needs 3 or 4 entrants, a tournament
needs a field, and a head to head needs someone on the other side. Until a
contest forms, no money is escrowed, nothing is graded, and nothing settles, so
none of the integration you actually want to test ever runs.

`services/test_opponents.py` fills the gap with throwaway practice opponents.
They enter through the same `enqueue()` the app uses for you, so the contest
forms through the real composition, escrow, and settlement path. They never
play, so at settlement they are refunded while you are graded normally.

They are excluded from the leaderboard and from the waiting list that feeds the
ticker, so they can never look like real activity.

---

## Step 1 — nothing to turn on

Testing behaviour follows **who is signed in**, not a setting.

Enter through **"Skip sign-up · enter the demo"** on the sign-in screen and you
get the sandbox:

- **Contests fill themselves.** Joining a pool, tournament or duel pulls in
  throwaway practice opponents, so a room forms on that same request instead of
  waiting forever for players who do not exist.
- **Casual games count.** Baselines, pool bars and tournament scores read
  unrated games too, including games against the Lichess computer. That is the
  quickest way to produce a finished game whenever you need one.

Sign in normally and you get production behaviour: rated games only, no
fabricated opponents. Both live in the same deployment, so every time you use
the real sign-in you are exercising the real thing.

There is nothing to remember to switch off. Turning off demo login
(`DEMO_LOGIN_ENABLED=false`) removes the sandbox and leaves production
untouched.

---

## Step 2 — start the stack

From the repo root:

```bash
make dev
```

That brings up Postgres in Docker, applies migrations, and starts the API
(`:8000`), the settlement worker, and the web app (`:5173`).

If you would rather run the pieces separately:

```bash
make db        # Postgres in Docker
make migrate   # apply migrations
make api       # API on :8000
make worker    # settlement worker (this is what grades finished games)
make web       # web app on :5173
```

The **worker matters**. It is the process that polls Lichess and settles
contests. Without it a pool will form and then sit there forever.

---

## Step 3 — link your Lichess account

1. Open <http://localhost:5173> and sign in.
2. Go to **Profile → Games**.
3. On the Chess row, press **Link**, type your Lichess username, press
   **Verify**.

That calls `GET /api/user/{username}` (see [`chess.md`](./chess.md) for the real
response) and stores your rating and history counts.

---

## Step 4 — build your metric baseline (do not skip this)

**If you linked chess before 2026-08-08, press Refresh on the Chess row now.**

Here is why. Pools quote your personal bar from a `MetricModel`, which is built
by `bootstrap()` from your game history. `bootstrap()` only models the metrics
listed in `GAME_RATE_METRICS`, and that list was **empty for chess** until the
`chess_moves` metric was added. So a link made before that date built no model,
and with no model every metric reads as "provisional", which the UI filters out.
That is why Solo Pools and Tournament looked empty.

**Refresh** re-runs `bootstrap()` and fixes it. One click, on the Chess row in
Profile.

One thing can still leave you with nothing: **no rated games at all**, because
bootstrap has nothing to model from. A single rated game is enough
(`STAT_BASELINE_MIN_N` is 1).

`GAME_HISTORY_FLOOR` is set to 20 for chess, but `meets_history_floor()` is
defined and never called, so it does not currently gate anything.

---

## Step 5 — join something

**Solo pool.** Play → Solo pools. You should see three cards, one per
difficulty, each showing a "Clear N" target. Pick an entry amount inside the
card and press **Join pool**. Three practice opponents enter the same bucket,
the room forms, and your entry escrows.

**Tournament.** Play → Tournament. Three cards: **Longest win streak**, **Total
wins**, **Fastest win**. Nine opponents fill the field.

**Head to head.** Play → Head-to-head. One opponent joins the queue and you
pair immediately.

Your contest appears in the right-hand rail under **In play**.

---

## Step 6 — play a real game and watch it settle

Go to Lichess and play a **rated** game. Then wait for the worker's next cycle.

What happens: the worker calls `GET /api/games/user/{you}` for the contest
window, `_normalize()` turns each game into a `NormGame`, and the metric is read
off it. For a pool, your first in-window game is compared to the room bar. For a
tournament, the window is scored by the metric's own rule (most wins, longest
streak, fewest moves in a won game).

The result lands in **Activity**, with your newest finished contest expanded so
the stat line is visible without clicking.

Windows are long by default: 24 hours for a pool, 48 for a tournament
(`POOL_WINDOW_SECONDS`, `TOURNAMENT_WINDOW_SECONDS` in `constants.py`). Shorten
them there if you want a faster loop.

---

## Why not a feature flag or an env var

This started as `TEST_OPPONENTS_ENABLED` and `STATS_COUNT_UNRATED` in `.env`,
and both are gone.

An environment switch applies to the whole deployment, so testing and production
behaviour could never coexist: flipping one to try something changed the rules
for every user at once, and you had to remember to flip it back. Tying the
behaviour to the demo account instead means the production path is never
special-cased, and it is exercised continuously by anyone signing in normally.

---

## If you still see nothing

Work down this list.

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Link your chess account" | Not linked | Profile → Games → Link |
| "No pools on this game yet" | No metric model | Profile → Chess row → **Refresh** |
| Still empty after refresh | No rated games to model from | Play one rated game, then Refresh again |
| Chess missing from the game switcher | Not in your play set | Profile → Games → tick the Chess checkbox |
| Join does nothing, no room forms | Signed in as a real account | Sign out, use "Skip sign-up · enter the demo" |
| Room forms but never settles | Worker not running | `make worker` |
| Tournament card shows no standings | Window still open | Standings refresh on a cadence; the window is 48h |

To confirm the switch is actually on, check the API log after a join. You should
see `testbot.pool_filled` with a `joined` count.

---

## Before you launch

```bash
# 1. Remove every practice opponent (cascades take their wallets and entries)
cd apps/api && uv run python -c "
import asyncio
from moneymatch_api.db.session import get_sessionmaker
from moneymatch_api.services import test_opponents

async def main():
    async with get_sessionmaker()() as s:
        print('purged', await test_opponents.purge(s))
        await s.commit()

asyncio.run(main())
"

# 2. Delete the scaffolding
rm apps/api/src/moneymatch_api/services/test_opponents.py
```

Then remove the three call sites that reference it (in `routers/pools.py`,
`routers/tournaments.py`, `routers/play.py`, each marked with a
"practice opponents (scaffolding, delete before launch)" comment), the
and `services/demo_mode.py`. The exclusion filters in `leaderboard.py` and
`matchmaking.py` go with them.

Nothing here reaches a real account in the first place, so a missed step is
untidiness rather than a production risk.
