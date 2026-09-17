# Money Match — Implementation Plan (phased, testable)

The build plan for the peer-to-peer 1v1 + tournament product. No bar, no house line. Keep the
bucketing (for *matchmaking*, not for a target). Track every game's stats per-game for the future.
Protect small fish, block smurfs/sandbaggers, and give admins a full audit + clawback trail.

**Ground rules (every phase obeys these — they're what keep us legal and safe):**
- **Peer-to-peer only.** Winners paid from the pot; we take a flat **rake** off the top. No number a player "beats" that we set. Bucketing decides *who you play*, never *what you wager against*.
- **Server-authoritative only.** Settle only on real, API-read matchmade games. Can't read it → **void + refund.** Never a screenshot or self-report.
- **Fail closed.** Missing/ambiguous/late data → void + refund. Never guess.
- **Deterministic + idempotent.** Same inputs → same result, always. A match can never be counted or paid twice. Everything reconstructable later.
- **Money as an abstraction.** The ledger works the same for **gems (now)** or real money (later). Start with gems.
- **Test alongside each phase.** No phase is "done" until its test gate passes on a fresh DB (migrations + logic). Work on a branch, merge on green.

> **Money as an abstraction.** Build the whole thing on **gems** first (a number in our ledger).
> Flipping to real money is a later config + compliance step, not a rewrite. This keeps us legal to
> test and lets us prove the loop before touching a payment processor.

---

## Phase 0 — Foundations

**Goal:** a skeleton that enforces the ground rules before any feature exists.

- Repo, migrations runner, config, a **deterministic clock** (so tests can fast-forward a 3-hour tournament), a background **worker + queue** (ingestion/settlement never block the API).
- A test harness that spins up a fresh DB, runs all migrations, seeds fake players/games.
- Define the **game registry**: each game has its own id, allowed modes, and its **rated stat spec** (which raw fields we keep, which single stat a contest can be scored on, mode gates). Example: CS2 → Competitive only, keep kills/kd/score, rate on kills; Chess → rated Blitz & Rapid kept separate.

**Test gate:** fresh DB migrates clean; worker processes a fake job; clock can advance in tests; registry rejects an unknown game/mode.

---

## Phase 1 — Data model + idempotent stat ingestion (keep everything, per-game)

**Goal:** every game a player plays is captured, once, with all raw stats, separated by game.

Core tables (sketch):

```
players(id, created_at, status, identity_fingerprint…)
game_links(id, player_id, game, external_id, UNIQUE(game, external_id))     -- one game account per game
match_stats(                                                                -- APPEND-ONLY, never edited
  id, player_id, game, host_match_id, mode,
  started_at, ended_at,
  rated_stat_value,          -- the one stat this game is scored on (e.g. kills)
  metrics JSONB,             -- FULL raw payload: keep everything for the future
  verified_source,           -- which API/GC confirmed it
  UNIQUE(player_id, game, host_match_id)   -- idempotency: a match counts once, ever
)
```

- **Per-game separation:** `match_stats` is one append-only table keyed by `game`, with a typed `rated_stat_value` plus a `metrics` JSONB holding that game's full raw stats. Per-game read views (`cs2_stats`, `chess_stats`) project the fields that game cares about. Adding a game = a registry entry + a view, not a schema rewrite. **We store more than we currently rate on** — that's the future dataset.
- **Ingestion is idempotent:** `INSERT … ON CONFLICT (player_id, game, host_match_id) DO NOTHING`. Re-ingesting the same match is a no-op.
- **Mode/patch gates:** only games in the allowed mode count (CS2 Competitive, Dota ranked, chess Blitz/Rapid). Wrong mode → ignored. Store the patch/version so a later rule change is auditable.

**Test gate:** ingest the same match 100× → exactly one row. Wrong-mode game → not counted. Raw metrics round-trip intact. Two games' stats never collide in the same row.

---

## Phase 2 — Skill index + buckets (per game) — smurf/sandbag resistant by construction

**Goal:** each player has one skill number per game, robust to gaming, and buckets that group similar players.

- **Skill index** per (player, game): the **mean of the best 40%** of the last N rated results. Why best-of: a **thrown game barely moves it**, so *sandbagging doesn't work by design.* (Derivative of the index w.r.t. a deliberately-bad game ≈ 0.)
- **Rise fast, fall slow:** the index climbs quickly on improvement but decays slowly, so you **can't tank your rating** to farm easier opponents.
- **12-month peak floor:** your index can't drop below a fraction of your demonstrated peak — another sandbag block.
- **Confidence:** track how many rated games back the index. Low confidence = new/uncertain player.
- **Buckets** per game: cut the skill range into a few bands (start with ~3–4). A player is in exactly one bucket per game. Buckets are for **matchmaking only**. (Min-variance cuts + hysteresis so players don't flap across a boundary — keep simple now, refine later.)

**Test gate:** feed a player great games + a few thrown ones → index tracks the good ones (sandbag-proof). A rapid tank attempt → index barely drops (peak floor holds). Same inputs → identical index (deterministic). Bucket assignment stable under tiny score wobble.

---

## Phase 3 — Wallet + double-entry ledger + escrow (gems now)

**Goal:** hold entries safely, pay winners, take rake — with money that can never be created or lost.

- **Double-entry ledger** (append-only). Every movement is two entries; nothing is ever deleted — reversals are *compensating entries*.
- **Escrow holds:** joining a contest **holds** your entry (can't be double-spent). Settlement **captures** it into the pot; a void **releases** it back.
- **Money invariant (asserted in code + tests):** `sum(balances) + sum(holds) + sum(rake) == sum(net deposits)` at all times.
- **Rake:** a fixed % taken off the pot at settlement, regardless of who wins. This is our only revenue and it's deterministic.

**Test gate:** the invariant holds after thousands of randomized concurrent joins/settles/voids. Double-join can't double-spend. A void restores the exact balance. Rake math exact to the cent/gem.

---

## Phase 4 — 1v1 engine + streak-progression matchmaking + fish protection

**Goal:** a full, live 1v1 loop, with the win-streak climb you described, that protects weak players.

**Matchmaking (the ladder you asked for):**
- Base: match within your bucket (similar skill).
- **Win → next match targets a slightly *higher* opponent.** Win again → higher still. Keep a transient **streak offset** that shifts your matchmaking target up on each consecutive win.
- **Lose → streak offset resets → back to a similar-stat opponent.**
- This climb is *matchmaking only* — it never changes what you wager against, and it's **also anti-smurf**: a smurf wins fast, the ladder rockets them up and *out of the fish pool* within a few matches, instead of letting them farm beginners.

**Fish protection (mechanics now; rewards later):**
- You're never matched against a far-higher player unless *you climbed there by winning.*
- A loss drops you back to your own level, not below — no tilt-farming you.
- New/low-confidence accounts get **stake caps** (e.g. gem ladder small→larger as confidence grows) — limits how much a smurf can take before the ladder pulls them up.
- Hooks reserved for later rewards (comeback bonus, loss-streak protection) — not built yet, just space left for them.

**1v1 lifecycle:** match → both stake (escrow hold) → each plays their real matchmade game in a window → we read both results → **higher rated stat wins pot − rake** → capture/payout. Any missing result / abandoned game → **void + refund**.
- *Cleanest form:* a game where the two can play **each other directly** (chess) — same conditions, no teammate luck. For games where they can't, each plays their own game and we compare (note: different lobbies add luck — legally weaker, flagged in the legal docs).

**Test gate:** full lifecycle end-to-end on gems. Win → next opponent is higher; 3-win streak climbs monotonically; a loss resets to same-stat. Abandoned game → void + exact refund. Stake cap enforced for a new account. Two far-apart players never matched at base.

---

## Phase 5 — Tournament engine (3-hour window, best game counts, top-3 split)

**Goal:** a live, async tournament exactly as specified.

**Config per tournament:** game, mode, **scored stat** (e.g. kills), **start time + duration (3h)**, entry fee, **rake %**, min/max players, prize split **60 / 25 / 15**, tie-break rule.

**How it runs (async — no need for players to be online at once):**
1. Players enter; entry is **held in escrow**. Pot = entries.
2. During the window each player plays their **own normal matchmade games**. We ingest each (Phase 1).
3. A player's **score = the highest scored-stat from games that *finished within* the window.** (Your "best of the games you played" rule.)
4. **Cutoff is hard:** a game still in progress when the clock hits 3h **does not count** — your last completed best stands. ("Too bad" — exactly as you said. Enforced by `ended_at ≤ tournament_end`.)
5. At end: rank by score desc; **tie-break deterministically** (earliest timestamp that reached that score, then fewer games used — never random). Top 3 get 60/25/15 of **(pot − rake)**.
6. **Underfill:** fewer than min players at close → **void + refund all** (never top up a prize — that would make us a house).

> **Honest note on "highest of N games" (MAX):** taking your *best* game rewards your luckiest game,
> which is *weaker* for the skill-vs-chance argument than an **average** would be. Keep MAX for feel
> if you want, but make the aggregation a **config knob** (`max` | `average` | `best-k-average`) so we
> can switch to average in stricter states without a rewrite. Also: kills in a *team* game carry the
> teammate-luck chance element (see the legal docs) — 1v1-native games (chess) are the clean version.

**Test gate (simulated with the deterministic clock):** run a full 3h tournament in fast-forward with many players playing overlapping games; scores = correct max of in-window games; a game crossing the cutoff is excluded; ranking + 60/25/15 split + rake exact; ties break deterministically; underfill refunds everyone exactly.

---

## Phase 6 — Anti-cheat: smurf / sandbag / collusion detection (flag, don't auto-ban)

**Goal:** catch the ways people game the system, surface them to admins, never silently punish.

- **Smurf:** covered structurally (Phase 2 best-of index rises fast + Phase 4 streak ladder pulls winners up + Phase 4 stake caps). Add a **flag** when a low-confidence account performs far above its bucket → admin review.
- **Sandbag:** covered structurally (best-of + fall-slow + peak floor). Add a **flag** on a pattern of obvious throws near contest boundaries.
- **Collusion / multi-account:** detect the **same human** (shared device / IP / payment fingerprint) entered in the **same contest or 1v1** → block entry + flag. Detect suspicious win-dumping between two accounts.
- **Anomaly flags → review queue, not auto-ban.** Improvement and cheating can look alike; a human decides. Every flag is logged with evidence.

**Test gate:** scripted smurf climbs out of the fish pool within N matches (structural defense works) *and* raises a flag. A sandbag pattern raises a flag. Two accounts sharing a fingerprint can't co-enter a contest. No legitimate improving player is auto-punished.

---

## Phase 7 — Disputes, clawback / refund, and the admin audit log

**Goal:** if a player reports cheating, admins can see everything and reverse money cleanly.

- **Everything is logged, append-only** (`audit_events`): every stat ingested, matchmaking decision, entry, settlement, payout, flag — with timestamps and the verifying source. A whole contest is reconstructable months later.
- **Payout hold window:** winnings settle but are **withheld from withdrawal** for a short window (e.g. 24h, config). This is what makes clawback possible *before money leaves.* (With gems, trivial; with real money, essential.)
- **Dispute flow:** a player reports cheating on a contest → creates a **dispute** → funds for that contest can be **held** → admin reviews.
- **Admin console (read-only over the log):** for any tournament, see **every game each participant played in the window** — the stat, timestamps, mode, and which API verified it — plus entries, standings, settlement math, and any flags. This is exactly the "check what happened" view you wanted.
- **Clawback = compensating ledger entries** (never edit history): reverse a payout, refund the pot, record who/why. Idempotent (a clawback can't double-apply).

**Test gate:** file a dispute inside the hold window → admin reverses → ledger returns to pre-payout state exactly, money invariant intact, full trail preserved. Reconstruct a finished tournament entirely from the log. Clawback applied twice = applied once.

---

## Phase 8 — Smoothness & hardening (make it pleasant, then stress it)

**Goal:** the things that make players stay, plus resilience.

- **Clear contest cards:** stat, window, entry, split, rake, tie-break — shown up front, plain language. Trust = our brand.
- **Live standings + notifications:** tournament start/end, your current rank, results, payout.
- **Matchmaking waits:** if no 1v1 opponent in-bucket, widen the search over time or queue; tournaments (async) sidestep this — lean on them when liquidity is thin.
- **Disconnect/abandon grace:** an abandoned or crashed game simply doesn't count; never punishes the player, never settles on it.
- **Compliance hooks (minimal now):** geo-gate (block hostile states in code), age gate — stubbed for gems, real before real money.
- **Monitoring:** distribution-drift alarms (a patch changed what a stat means), settlement backlog, void/refund rates, flag rates.

**Test gate:** end-to-end live playtest with real humans on gems — a full 1v1 ladder run and a full 3h tournament — with no stuck contests, correct payouts, working disputes, and a clean admin log. Load-test settlement at 10× expected concurrency.

---

## Build order at a glance

| Phase | Delivers | The one thing its test must prove |
| --- | --- | --- |
| 0 | Foundations, registry, clock, worker | Fresh DB migrates; unknown game rejected |
| 1 | Per-game idempotent stat capture | A match counts exactly once; raw stats kept |
| 2 | Skill index + buckets | Sandbag/tank can't move the number |
| 3 | Wallet + ledger + escrow | Money invariant never breaks |
| 4 | 1v1 + streak ladder + fish protection | Win climbs, loss resets; void refunds exactly |
| 5 | 3h best-of tournament, top-3 split | Cutoff excludes in-progress game; split/rake exact |
| 6 | Smurf/sandbag/collusion flags | Attacks flagged; no false auto-bans |
| 7 | Disputes, clawback, admin log | Clawback reverses cleanly; contest reconstructable |
| 8 | Polish + resilience | Live human playtest passes end-to-end |

---

## Other issues & ideas worth building in early (cheap now, painful later)

- **One game account per game per person** (`UNIQUE(game, external_id)`) — stops trivial multi-accounting.
- **Aggregation as a config knob** (`max`/`average`) so we can tune the legal skill-vs-chance posture per state without a rewrite.
- **Season/reset support** for buckets later — leave the versioning column now.
- **Everything peer-funded, never a guaranteed prize** — underfill always voids, never tops up (keeps us out of "house" territory).
- **Skill-agnostic core + per-game adapter boundary** — so game #2 (and one day fitness/other skills) is an adapter, not a rewrite. No game name in the core logic.
- **Show players their bucket and streak** — legible "why am I matched here" builds trust.
- **Refund-first instinct** — when in doubt, void and refund; it's cheaper than a dispute and better for trust.

---

## What we are explicitly NOT building yet

Real-money rails / KYC (gems first), the reward/bonus system (hooks only), more than one game (prove the loop on one — chess is cleanest), auto-growing bucket counts, and the "any skill" expansion. Simple now; complexity later, once the loop is proven.
