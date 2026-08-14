# CS2 baseline — 2026-08-11, before any ship-day changes

Captured by `scripts/demo/cs2_dryrun.py` against the live database inside a
transaction that was rolled back. This is the "before" picture for the changes
in the `demo/cs2-ship` branch.

Reproduce with:

```bash
apps/api/.venv/Scripts/python.exe scripts/demo/cs2_dryrun.py
```

---

## Result

```text
# cs2.faceit dry run
user=demo metric=cs2_kd_ratio entry=$10.00
practice opponents enabled: True
seeded the demo fixture (same call /demo/login makes)

## Solo pool
status before: idle
  easy    opponents=3 formed    room_size=4 room_bar=1.25 pot=$40.00
  medium  opponents=3 formed    room_size=4 room_bar=1.35 pot=$40.00
  hard    opponents=3 formed    room_size=4 room_bar=1.45 pot=$40.00
  preview: provisional=False n=25
    easy    bar=1.25     clears 32%
    medium  bar=1.35     clears 18%
    hard    bar=1.45     clears 9%

## Tournament
status before: formed
  already in: game=chess.lichess metric=chess_win_streak state=LOCKED
  opponents=9 status=formed
  game=chess.lichess metric=chess_win_streak state=LOCKED pot=$250.00

## Head to head
  [warning] testbot.queue_join_failed  error='Not enough recent matches to duel
            on this stat yet' handle=testbot_ada
  kd_ratio       kind=stat_race  opponents=0 status=searching
  adr            kind=stat_race  opponents=0 status=searching
  headshot_pct   kind=stat_race  opponents=0 status=searching
  win_next       kind=win_next   opponents=1 status=matched
```

| Mode | Baseline |
| --- | --- |
| Solo pool | Works. Rooms of 4 at all three tiers. |
| Tournament | Returns the **chess** contest, not a CS2 one. |
| H2H stat duels | 0 opponents, stuck searching. |
| H2H `win_next` | Works. |

---

## One thing the report got wrong

`docs/game/cs2-demo.md` says the demo's CS2 metric models are seeded at
`mu=1.15 / sigma=0.22 / n=25`. That is true **only just after a demo login**.

The stored state on disk right now is `mu=0, sigma=0, n=0` for all three CS2
metrics, and the same for Dota and PUBG. Chess is unaffected.

The cause is a metric bootstrap running against the synthetic host handle
(`host_username='demo'`), which resolves to no FaceIt player, returns an empty
history, and upserts a zeroed model over the seeded one. A zeroed model reads as
provisional and hides every card.

It repairs itself on the next demo login, because `_ensure_demo_fixture`
restores any model whose `n` is below the baseline floor rather than skipping on
row existence alone. So the user-visible behaviour is the table above; the raw
stored state between logins is worse.

Run with `--no-seed` to see the unseeded state:

```text
  easy    FAILED PoolError: Play a match on this stat first
  preview: provisional=True n=0
```

This matters for ship day only in that **nothing should read the demo's CS2
baseline as authoritative until the account is relinked to a real FaceIt
nickname** (phase 2.1). Until then every bar above is quoted from fabricated
numbers.
