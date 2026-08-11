# Implementation Prompt — CS2 Wager Demo, Ship Today

> **How to use this file:** paste it to a coding agent running inside the repo.
> It is written to be executed top-to-bottom. The phase gates are not advisory.

---

## Your mission

There is a live demo **tomorrow**. By end of today a user must be able to:

1. Attach their CS2 account to the app
2. Join a wager — solo pool, tournament, or head-to-head
3. Be matched with practice opponents **of similar Elo**
4. Play a **real FACEIT match**
5. Have the wager settle — pass or fail — from that match's real stats

Everything else is secondary to those five steps working end to end.

## Non-negotiable rules

1. **Read before you edit.** This document describes the codebase from a report
   written 2026-08-11. Line numbers, function bodies and even file paths may
   have drifted. Open every file named here and confirm before changing it. If
   what you find contradicts this document, **trust the code** and say so.
2. **The phase gates are real.** Do not start phase N+1 until phase N's
   Definition of Done passes. If you are running out of time, it is far better
   to deliver phases 0–2 working than all six phases half-done.
3. **Never break the FACEIT path.** It is the demo. Phases 3–5 are additive and
   must sit behind feature flags that default to OFF.
4. **No silent failures.** The bug in phase 1 exists because an `except
   Exception` swallowed an error and the UI sat on "searching" forever. Every
   `except` you touch or add must log with context.
5. **Commit per phase**, on a branch, with the phase number in the message. You
   need to be able to roll back to a working demo in one command.
6. **Ask before destructive DB work.** Do not drop, truncate or migrate
   destructively without confirming.

## Known repo map

From the report's section 7. Verify each before use.

| Concern | File |
| --- | --- |
| FACEIT HTTP client, TTL cache | `services/hosts/faceit.py` |
| Normalisation, metric extraction | `adapters/cs2_faceit.py` |
| Metric registry, floors, increments | `constants.py` |
| Head-to-head market definitions | `services/markets.py` |
| Practice opponents (scaffolding) | `services/test_opponents.py` |
| Demo seeding and relink | `routers/demo.py` |
| Tournament engine | `services/tournament_engine.py` (approx) |
| Rating prior | `services/skill_prior.py` (approx) |

---

# PHASE 0 — Safety net first (target: 30 min)

**Do this before touching any business logic.** The single largest risk to
tomorrow is a live demo that depends on a 40-minute CS2 match completing
correctly in front of an audience. Build the escape hatch first, while you are
calm and have time.

## 0.1 Branch and baseline

```bash
git checkout -b demo/cs2-ship
```

Record the current state so you can prove what you changed. Run each of the
three modes against the live DB **inside a rolled-back transaction** (the report
author did exactly this — find and reuse their script if it is committed) and
save the output to `docs/game/cs2-baseline-$(date +%F).md`.

## 0.2 Build the simulate-result endpoint

Add an admin-only endpoint that injects a finished, gradeable match for a user
without any external API call:

```
POST /api/v1/demo/simulate_result
{
  "game": "cs2.faceit",
  "user_id": "<uuid>",
  "metrics": { "cs2_kd_ratio": 1.62, "cs2_adr": 91.3, "cs2_headshot_pct": 54.0 },
  "rounds": 22,
  "won": true,
  "played_at": "2026-08-12T15:04:00Z"
}
```

Requirements:

- It must write through **the same code path the real settlement worker reads**.
  Do not special-case it downstream. If the real path reads a `matches` table,
  write a row to `matches`. The whole point is that the rest of the system
  cannot tell the difference.
- Gate it behind an admin check **and** an env flag `DEMO_SIMULATE_ENABLED`.
- Log loudly every time it fires, including in the response body, so nobody
  ever mistakes a simulated settlement for a real one.

## 0.3 Build force-settle

Tournaments only settle at the 48-hour window close (report §5). You cannot
wait 48 hours on stage. Add:

```
POST /api/v1/demo/force_settle   { "contest_id": "<uuid>" }
```

which runs the settlement worker's logic for one contest immediately. Same
admin gate, same loud logging.

## Definition of Done — Phase 0

- [ ] `simulate_result` produces a settled wager end to end, with the money
      moving, and the settlement is indistinguishable downstream from a real one
- [ ] `force_settle` closes a formed tournament immediately
- [ ] Both are off unless `DEMO_SIMULATE_ENABLED=1`
- [ ] Committed

> **You now have a demo that cannot fail.** Everything after this is upside.

---

# PHASE 1 — Fix the three known defects (target: 90 min)

All three are diagnosed in the report. All three are small. Do them in this
order; the third is what makes your demo narrative true.

## 1.1 Stat duels return zero opponents

**Symptom:** `kd_ratio`, `adr`, `headshot_pct` head-to-head markets sit on
`status=searching` with `opponents=0` forever.

**Cause:** `services/test_opponents.fill_queue` calls `_prepare(...)` with
`metric=None`. `_prepare` uses that argument to decide which of your metric
models to mirror onto the practice opponent, so `None` creates an opponent with
**no metric model**. The subsequent enqueue then fails its own baseline check
with `detail={'metric': 'cs2_kd_ratio', 'n': 0}`, and that error is swallowed by
an `except Exception` inside `fill_queue`.

**Fix:** thread the market's metric through to `_prepare`.

- Find where the market definition lives (`services/markets.py`) and how a
  market maps to its metric key. Stat-duel markets have one; brokered markets
  like `win_h2h` and `win_next` have none.
- Pass that metric into `_prepare`. When the market has no metric (`win_next`),
  keep passing `None` — that path works today and must keep working.
- **Do not remove the `except Exception`.** Scaffolding must never 500 a real
  user request. But make it `log.exception(...)` with the market, game and user
  id, and surface a debug-only field in the response so this class of bug is
  visible next time instead of silent.

**Verify:** all four CS2 head-to-head markets reach `status=matched` with
`opponents=1`. Confirm `win_next` did not regress.

## 1.2 Tournament join returns the wrong game's contest

**Symptom:** a CS2 tournament join silently returns a locked **chess**
tournament.

**Cause:** `tournament_engine._current_tournament_for_user` has no game filter:

```python
select(Tournament).join(TournamentEntry)
  .where(TournamentEntry.user_id == user_id, Tournament.state == "LOCKED")
```

Any locked tournament on any title short-circuits `enqueue`.

**Fix:** add the game predicate.

```python
.where(
    TournamentEntry.user_id == user_id,
    Tournament.state == "LOCKED",
    Tournament.game == game,          # confirm the real column name
)
```

Trace the call site to make sure `game` is in scope; if it is not, thread it
through. Check whether the "one locked tournament per user" rule is intended to
be **per game** or **per user globally** — this fix assumes per game, which is
what the report implies is wanted. If any other code depends on the global
behaviour, flag it rather than silently changing semantics.

**Note:** the demo account's blocking chess tournament has a window closing
**2026-08-11 20:00 UTC**, so it will free itself today regardless. Fix the
filter anyway — you cannot ship a rule where a chess entry blocks a CS2 entry.

**Verify:** with a locked chess tournament present, a CS2 tournament join
creates a **new CS2 contest**, field of 10, nine practice opponents.

## 1.3 Matchmaking ignores Elo — this is the one your audience will notice

**Symptom:** your demo narrative is "matched with players of similar Elo".
Today CS2 brackets on the metric model (mu/sigma of K/D), not on FACEIT Elo.

**Cause:** `faceit_elo` **is** captured at link time in
`ProfileSnapshot.rating`. Nothing reads it. `skill_prior.host_rating()` is the
only rating reader and it looks for chess-shaped fields:

```python
formats = snapshot.get("formats") or []
if not formats:
    return None          # always, for CS2
```

**Fix:** fall back to the generic rating.

```python
formats = snapshot.get("formats") or []
if not formats:
    rating = snapshot.get("rating")
    return float(rating) if rating is not None else None
# ... existing chess path unchanged
```

This one change makes FACEIT Elo, Dota MMR and every other title's generic
rating available to the code path chess already uses.

**Then check the consumer.** Making `host_rating` return a number is only half
the job — confirm that pool/tournament bracketing and practice-opponent
generation actually *use* it. If `_prepare` seeds practice opponents without
reference to the host's rating, seed them within a band (e.g. ±150 Elo) so the
"similar Elo" claim is literally true and visible in the UI.

**Verify:** join a CS2 pool and confirm the practice opponents' ratings cluster
around yours. Confirm chess bracketing is byte-identical to before.

## Definition of Done — Phase 1

- [ ] All four CS2 h2h markets match; `win_next` not regressed
- [ ] CS2 tournament join creates a CS2 contest while a chess one is locked
- [ ] `host_rating` returns FACEIT Elo; opponents visibly cluster near the user
- [ ] Chess regression-tested end to end — **you changed shared code**
- [ ] Committed

---

# PHASE 2 — Make it real (target: 2–3 h) ← **the demo lives here**

Until this phase, no CS2 call leaves the building. The demo user's CS2 link is
a seeded placeholder: `host_username='demo'`, with three hand-written metric
rows (`cs2_kd_ratio` mu 1.15, `cs2_adr` mu 78.0, `cs2_headshot_pct` mu 47.0,
all `n=25`). Every bar and payout you have seen so far was computed from
fabricated inputs. The maths is real; the data is not.

## 2.1 Relink to a real FACEIT account

```
POST /api/v1/demo/relink   { "game": "cs2.faceit", "username": "<REAL_NICK>" }
```

This path is game-generic and already works — it is how chess was relinked.

**Watch the bootstrap cost.** It is one `/players` call, one `/history` call,
and **one `/matches/{id}/stats` call per match**, and the account needs at least
`GAME_HISTORY_FLOOR = 25` CS2 matches to clear the history gate. That is 25+
sequential FACEIT API calls.

Before running it:

- Read `services/hosts/faceit.py` and confirm the TTL cache and whether there is
  any rate-limit handling. If there is none, add bounded concurrency and
  exponential backoff on 429 **now**, not after you have been throttled.
- Run the relink **once**, early. Do not leave it until the last hour, and do
  not re-run it casually on demo morning.

**Verify:** the account clears the history gate and the metric models are
rebuilt from real matches — the tell is that mu/sigma stop being round numbers
and `n` is no longer exactly 25.

## 2.2 Add CS2 eligibility rules

Report §6: for CS2 the eligibility rules are **"None yet"**. Chess enforces
rated / real time control / human / min moves. CS2 enforces nothing, which
means a 3-round surrendered stomp grades the same as a real match. On a wager
product that is the biggest open collusion hole you have.

The FACEIT feed carries two usable signals. Implement both:

- **`round_stats.Rounds`** — a real match runs ~22 rounds. Reject anything under
  a floor (start at **16**; a 13–3 win is the shortest legitimate full match).
- **`competition_type`** — accept `matchmaking`, reject `championship`, which is
  a privately arrangeable lobby.

Put the floor in `constants.py` next to the other per-game floors, not inline.

**Verify:** a match below the round floor is skipped by grading rather than
counted, and the skip is logged with a reason.

## 2.3 Prove the settlement path end to end

This is the rehearsal. Do not skip it.

1. Relinked demo user joins a **solo pool** at a low entry.
2. Confirm the room forms, three practice opponents join, escrow is taken, and
   the bar is quoted from the **real** rebuilt baseline.
3. Play a real FACEIT match. *(Wingman-style speed is not available on FACEIT —
   budget ~40 minutes and 10 players. Plan this for the afternoon, not the
   evening.)*
4. Confirm the settlement worker picks up the first qualifying match in the
   window, compares the metric against the room bar, and settles. Pools settle
   early once every entrant is decided; practice opponents never play, so they
   grade as a miss and their entries fund the clearers.
5. Repeat for **head-to-head `win_next`** — it needs no metric and is the most
   reliable live demo.
6. For **tournament**, form it and settle with `force_settle` from phase 0. Its
   real window is 48 hours; you are not waiting for that on stage.

## 2.4 Understand what you cannot claim

Be straight with your audience about one thing, because a sharp viewer will ask.
CS2 is **5v5**. Your K/D depends on nine other people, four of whom want you to
fail and four of whom can carry you. A solo-pool bar quoted from your own
history still works as a self-comparison, but the variance is not all yours, and
stacking with friends is a legitimate way to move your own average.

Also: a CS2 head-to-head is **coordinated, not brokered**. `CS2FaceitAdapter`
does not implement `create_match`, and the base class raises
`NotImplementedError`. Chess can open a challenge restricted to two accounts and
grade that exact game id; FACEIT has no equivalent the Data API can drive. Each
player plays their own next match and the two results are compared. Do not build
UI copy that implies the platform put two people in the same lobby — it cannot.

## Definition of Done — Phase 2

- [ ] Demo account relinked to a real FACEIT nick, ≥25 real matches ingested
- [ ] Metric models rebuilt from real history (non-round mu/sigma)
- [ ] Round floor and `competition_type` filter enforced and logged
- [ ] **One real FACEIT match has settled one real wager end to end**
- [ ] Tournament settles via `force_settle`
- [ ] Committed

> ### 🛑 HARD GATE
>
> **If phase 2 is not done, stop here and rehearse the demo.** Everything below
> is production hardening that your audience will not see tomorrow. A polished
> demo of phases 0–2 beats a broken demo of phases 0–5. Re-read this paragraph
> before you start phase 3.

---

# PHASE 3 — Steam identity, additive (target: 2 h) — flag: `STEAM_IDENTITY_ENABLED`

Your app currently identifies CS2 players by **FACEIT nickname**. For
production that is a weak primary key: nicknames are mutable, and the FACEIT
link proves nothing about who owns the Steam account underneath.

Add Steam OpenID login **alongside** the existing FACEIT link. Do not replace
it. Do not make it required for the demo path.

- **Steam OpenID** ("Sign in through Steam") → SteamID64. This is the only
  identity method that cryptographically proves ownership. For a money product
  it is eventually mandatory.
- `ISteamUser/GetPlayerBans` on link — VAC/game ban check before accepting a
  wager. Cheap, and you want it.
- `ISteamUserStats/GetUserStatsForGame` (`appid=730`) for profile flavour.
  **Never settle on it** — it is lifetime-cumulative across casual, deathmatch
  and bot games, and it requires the profile's "Game details" to be public.
- `ISteamUser/ResolveVanityURL` as a fallback for pasted profile URLs. Note it
  resolves a **custom profile URL only**, never a display name — Steam display
  names are neither unique nor searchable, and accepting one as identity is an
  impersonation vector on a wager app.

Store SteamID64 as a new column on the user's CS2 link. The demo path must
continue to work with it NULL.

**Definition of Done:** a user can attach Steam, see their ban status, and the
entire phase-2 flow still works with the flag off.

---

# PHASE 4 — Valve share-code ingestion, dark (target: 2 h) — flag: `VALVE_INGEST_ENABLED`

**This will not be demoed tomorrow.** Its value is that it starts accumulating
data today which you cannot recover later. Build it, turn it on, show nobody.

**Why it is time-sensitive:** share codes never expire, but the demo files they
point at **expire roughly one month after the match**. Every day this poller is
not running is a month of matches you can never analyse.

1. Vendor the share code codec (base-57 → `match_id` u64, `outcome_id` u64,
   `token_id` u16). A round-trip-tested implementation is in the attached
   `sharecode.py`. **Validate it once against a real share code from your own
   match history before trusting it.**
2. Onboarding collects the user's **Match History Authentication Code**
   (help.steampowered.com → CS2 → Access to Game Data) plus **one** share code
   as a starting cursor.
3. Cron the chain walker against
   `ICSGOPlayers_730/GetNextMatchSharingCode/v1/`. Handle the status codes
   properly: `202` = caught up (normal, not an error); `412` = the known code
   does not belong to that steamid, so **stop and re-prompt the user, do not
   retry**; `403` = bad auth code; `429`/`503` = back off. Repeated bad auth
   codes get you temporarily blocked.
4. Persist every code and the per-user cursor. **Storing the codes is the whole
   deliverable of this phase.** Do not attempt to resolve them to demos yet.

**Definition of Done:** codes accumulating in a table, cursor advancing, flag
off in the demo environment.

---

# PHASE 5 — Explicitly out of scope today

Write these up as tickets. Do not start them.

- **GC sidecar.** A share code does not contain a download URL. Getting one
  requires Valve's Game Coordinator — protobuf over the Steam network, via
  `CMsgGCCStrike15_v2_MatchListRequestFullGameInfo`, from a logged-in Steam
  account that owns CS2. Python's library for this is unmaintained; the
  realistic shape is a small Node sidecar (`steam-user` + `globaloffensive`)
  exposing one endpoint, share code in → demo URL out. Note the GC exposes only
  the **last 8 matches**, which is exactly why phase 4's chain matters.
- **Demo download and custody.** Pull the `.dem.bz2` to object storage
  immediately on discovery (~50–150 MB each). The stored demo is your audit
  trail — the artifact you show a user who disputes a payout.
- **Parse worker.** `demoparser2` in a queue. It yields events and ticks, not
  stats; K/D, ADR, HS%, KAST and opening duels are all things you compute.
  Budget days, not hours, for numbers that match what csstats.gg shows.
- **Two-chain verification.** Once both parties are enrolled with auth codes,
  the same match appears in **both** of their share-code chains. Two independent
  Valve-attested chains containing the same `match_id` proves they played each
  other, before you have parsed anything — then the demo confirms the score.
  Neither party can fake it. This is the endgame for brokered CS2 duels and it
  is the one thing FACEIT's API cannot give you.

---

# Demo runbook — print this and follow it tomorrow

**The night before**

- [ ] Relink already done and verified — **do not re-run it on demo morning**
- [ ] `DEMO_SIMULATE_ENABLED=1`, `STEAM_IDENTITY_ENABLED` and
      `VALVE_INGEST_ENABLED` off
- [ ] Chess tournament entry cleared or expired
- [ ] Full dry run of every step below, start to finish
- [ ] Working commit tagged: `git tag demo-ready`

**On stage, in this order** — safest first, so a failure late still leaves you
having shown a working product

1. **Attach account** — relink to the real FACEIT nick, show the real baseline
   populate. (Steam login too, if phase 3 landed.)
2. **Head-to-head `win_next`** — most reliable, needs no metric.
3. **Solo pool** — three practice opponents at similar Elo, escrow, live bar.
4. **Tournament** — field of 10, then `force_settle` to show the payout.
5. **Live match** — only if the schedule genuinely allows 40 minutes. Otherwise
   pre-play the match before the demo and show the settlement landing.

**If something breaks:** `simulate_result` from phase 0. Say plainly that you
are injecting a result to show the settlement path; do not pretend it is live.
An audience forgives a stubbed input far more readily than a demo that hangs.

---

## Report to the user when you finish

State plainly:

1. Which phases actually reached Definition of Done
2. Anything in this document that contradicted the real code, and what you did
3. Anything you changed that touches **chess** (`host_rating` and the tournament
   filter both do) and how you regression-tested it
4. The exact commands to run the demo, and the exact rollback command
