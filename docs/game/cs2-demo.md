# CS2 demo — what works today, per game mode

> **Retired.** FACEIT was removed on 2026-08-12; CS2 now settles from
> Valve share codes via `cs2.steam`. Kept as the record of what the FACEIT
> integration actually returned, which is why the parsing decisions in
> `docs/game/cs2-steam.md` look the way they do. Nothing here describes
> current behaviour.


Written **2026-08-11** by reading the code and then running each mode against
the live database inside a rolled-back transaction. Every number below is from
an actual run, not from reading the source and hoping.

Companion to `docs/game/cs2.md`, which is the raw API capture.

---

## The short version

| Mode | State today | What blocks it |
| --- | --- | --- |
| **Solo pool** | **Works** | Nothing |
| **Tournament** | **Works, but the demo account cannot enter one right now** | One locked tournament per user, across all games |
| **Head-to-head — stat duels** | **Broken** | Practice opponents have no CS2 baseline |
| **Head-to-head — win your next match** | **Works** | Nothing |

And one thing that is true of all three: **the demo's CS2 identity is
fabricated**, so nothing currently touches the FaceIt API at all.

---

## 0. The demo's CS2 account is not a real account

This is the single most important fact before a live test.

The shared demo user's CS2 link is a **seeded placeholder**:

```
host_username = 'demo'      status = active
rating        = None        rank_label = 'FACEIT'      total_games = 120
```

There is no FaceIt player behind it. `donk666` or your own nickname would
resolve to a `player_id`; `demo` resolves to nothing.

Its metric models are seeded too, from `_DEMO_METRIC_FIXTURE` in
`routers/demo.py`, not bootstrapped from match history:

| Metric | mu | sigma | n |
| --- | --- | --- | --- |
| `cs2_kd_ratio` | 1.15 | 0.22 | 25 |
| `cs2_adr` | 78.0 | 12.0 | 25 |
| `cs2_headshot_pct` | 47.0 | 8.0 | 25 |

`n = 25` is deliberate: it clears every baseline floor so the demo never reads
as provisional. The round numbers are the tell that these are hand-written.

**Consequence:** every bar, every payout and every room you have seen on CS2 so
far was computed from these three fabricated rows. The maths is real; the inputs
are not. Contrast chess, where the demo was relinked to a real Lichess account
and the models were rebuilt from real games.

**To do a live test**, relink first:

```
POST /api/v1/demo/relink   { "game": "cs2.faceit", "username": "YOUR_FACEIT_NICK" }
```

That path is game-generic, so it works for CS2 exactly as it did for chess. It
rebinds the link and re-bootstraps the metric models from real FaceIt history,
which is one `/players` call, one `/history` call and **one `/matches/{id}/stats`
call per match**.

---

## 1. Solo pool — works

Verified by joining all three difficulties at a $10 entry:

```
easy    bots=3  status=formed  room_size=4  room_bar=1.25  pot=$40.00
medium  bots=3  status=formed  room_size=4  room_bar=1.35  pot=$40.00
hard    bots=3  status=formed  room_size=4  room_bar=1.45  pot=$40.00

preview: provisional=False  n=25
  easy    bar 1.25   clears 32%
  medium  bar 1.35   clears 18%
  hard    bar 1.45   clears  9%
```

Rooms form, three practice opponents join, escrow is taken, and the bars are
quoted from the seeded baseline. Metrics available: `cs2_kd_ratio`, `cs2_adr`,
`cs2_headshot_pct`.

Note the bars behave the *opposite* way to chess: K/D is a rate where bigger is
better, so a harder tier asks for **more**. Only `chess_moves` is in
`METRIC_LOWER_IS_BETTER`, and only `chess_moves` gets the lognormal treatment
and the win requirement. CS2 bars are plain `mu + k*sigma` on a normal.

Grading reads the first qualifying match in the window and compares its
`cs2_kd_ratio` against the room bar. Practice opponents never play, so they are
graded as a miss and their entries fund the clearers.

---

## 2. Tournament — works, but the demo cannot enter one right now

The engine is fine. The blocker is a rule, not a bug:

```python
# tournament_engine._current_tournament_for_user
select(Tournament).join(TournamentEntry)
  .where(TournamentEntry.user_id == user_id, Tournament.state == "LOCKED")
```

There is **no game filter**. Any locked tournament, on any title, makes
`enqueue` return that one instead of creating a new contest. The demo account is
currently locked into a **chess** tournament (`chess_win_streak`, window closing
2026-08-11 20:00 UTC), so a CS2 tournament join silently returns the chess one:

```
=== TOURNAMENT ===
status before: formed
bots=9  status=formed
pot=$250.00  state=LOCKED  field=10
window 2026-08-09 20:00 -> 2026-08-11 20:00     <- the chess contest
```

`cancel()` does not help: it only removes a *waiting ticket*, never a locked
contest. So the options are to wait for the window to close, settle it early, or
clear the entry directly.

Once free, a CS2 tournament forms the same way chess does: field of 10, minimum
6, nine practice opponents fill the rest, scored on the mean of your first three
qualifying matches.

---

## 3. Head-to-head — half of it works

CS2 has four markets, and they behave differently.

### Stat duels (`kd_ratio`, `adr`, `headshot_pct`) — broken

```
kd_ratio       opponents=0  status=searching
adr            opponents=0  status=searching
headshot_pct   opponents=0  status=searching
```

The cause is in `test_opponents.fill_queue`, which calls `_prepare(...)` with
**`metric=None`**. That is what tells `_prepare` to mirror your metric model
onto the opponent, so with `None` the practice opponent is created with **no
metric model at all**. The enqueue then fails its own baseline check:

```
PoolError/MatchmakingError  detail={'metric': 'cs2_kd_ratio', 'n': 0}
```

It is swallowed by the `except Exception` inside `fill_queue` (scaffolding must
never 500 a real request), which is why the UI just sits on "searching" with no
error.

This never showed up on chess because chess's only head-to-head market is
`win_h2h`, a **brokered** duel with no metric behind it.

The fix is small and belongs in the scaffolding: pass the market's metric
through to `_prepare` so a stat-duel opponent gets a mirrored baseline.

### Win your next match (`win_next`) — works

```
match.formed  game=cs2.faceit  market=win_next  match_id=c8841e3e-...
win_next       opponents=1  status=matched
```

No metric needed, so the opponent enqueues cleanly and a match forms.

### There is no brokered CS2 duel, and there cannot be

`CS2FaceitAdapter` does not implement `create_match`, so the base class raises
`NotImplementedError`. Chess can open a challenge restricted to two accounts and
grade that exact game id. FaceIt has no equivalent the Data API can drive.

So a CS2 head-to-head is always **coordinated**, not brokered: each player plays
their own next match on their own, and the two results are compared. Two people
in the same FaceIt lobby is a coincidence the platform cannot arrange or verify.

---

## 4. Matchmaking is not on Elo, and the Elo is right there

`faceit_elo` **is** captured at link time, in `ProfileSnapshot.rating`. Nothing
reads it for matchmaking.

`skill_prior.host_rating()` is the only rating reader, and it looks for the
chess-shaped fields:

```python
formats = snapshot.get("formats") or []
if not formats:
    return None                      # <- always, for CS2
```

`formats` and `primary_speed` are populated by chess only; the schema comment
says so. So for CS2 that function returns `None`, and:

- **pools and tournaments** bracket on the **metric model** (mu/sigma of K/D
  or ADR), not on FaceIt Elo;
- **head-to-head** pairs on the same metric baselines plus the anti-collusion
  checks.

That is defensible for a stat contest (matching on the stat you are betting on
is arguably better than matching on Elo), but it is not what "matchmaking to
similar Elo" means, and it is not what a demo audience will assume they are
seeing.

Making it Elo-aware is a small change with a clear shape: teach `host_rating` to
fall back to `snapshot["rating"]` when `formats` is empty. That one line makes
FaceIt Elo, Dota MMR and any other title's generic rating available to the same
code path chess already uses.

---

## 5. What a live CS2 test needs

In order:

1. **Relink the demo to a real FaceIt nickname** (section 0). Until then no CS2
   call leaves the building.
2. **Confirm the bootstrap found matches.** The account needs at least
   `GAME_HISTORY_FLOOR` = **25** CS2 matches to clear the history gate, and the
   bootstrap is one stats request per match.
3. **Free the tournament slot** if you want to test tournaments (section 2).
4. **Fix `fill_queue`** if you want to test stat duels (section 3). `win_next`
   works today with no changes.
5. **Play a real FaceIt match**, then wait for the settlement worker. Pools
   settle early once every entrant is decided; tournaments only at the 48-hour
   window close.

---

## 6. Differences from chess worth remembering

| | Chess (Lichess) | CS2 (FaceIt) |
| --- | --- | --- |
| API key | None | Required |
| Requests per poll | 1 | 1 + **one per match** |
| Head-to-head | Brokered, exact game id | Coordinated, compare two results |
| Rated vs casual | Real distinction, enforced | No such flag; everything is rated |
| Eligibility rules | Rated, real time control, human, min moves | **None yet** |
| Metric direction | `chess_moves`, fewer is better | Rates, more is better |
| Team game | No | **Yes, 5v5** |

The last row is the one with teeth. Your K/D in a 5v5 depends on nine other
people, four of whom want you to do badly and four of whom can carry you. A solo
pool bar quoted from your own history still works as a self-comparison, but the
variance is not all yours, and stacking with friends is a legitimate way to move
your own average.

None of the chess anti-collusion work applies here yet: there is no move floor,
no bot check and no rated filter for CS2, because the FaceIt feed carries none
of those signals. The nearest usable ones are `round_stats.Rounds` (a real match
runs ~22 rounds) and `competition_type` (`matchmaking` versus an arrangeable
private `championship`).

---

## 7. Where the code lives

| Concern | File |
| --- | --- |
| HTTP client, TTL cache | `services/hosts/faceit.py` |
| Normalisation, metric extraction | `adapters/cs2_faceit.py` |
| Which metrics exist, floors, increments | `constants.py` |
| Head-to-head market definitions | `services/markets.py` |
| Practice opponents | `services/test_opponents.py` |
| Demo seeding and relink | `routers/demo.py` |
