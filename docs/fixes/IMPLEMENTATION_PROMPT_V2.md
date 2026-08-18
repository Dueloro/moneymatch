# Implementation brief — round two

Four workstreams. Attach `HYBRID_BRIEF.md`, `hybrid_study.py` and this file.

**Supersedes:** `ROOM_BAR_BRIEF.md` (the gated floor is dropped — see workstream D).
**Unchanged:** every ground rule in `IMPLEMENTATION_PROMPT.md` — test-as-you-go, one logical change
per commit, money invariants untouchable, fail closed, don't touch production, write down what you
had to assume. Branch stays `fixes/testing`.

**Order.** Phase 2.0 model versioning first — all four workstreams below move a quoted number and
are gated on it. Then A → B → C → D, because A changes the universe the others apply to.

**Stop and report** after B and after D.

---

## A. Lock CS2 to Competitive only

Product decision: for now CS2 means **Competitive and nothing else**. Premier and Wingman are out.
Build it as a *configurable allow-list*, not a hard-coded assumption — other modes are coming back
later and I don't want this dug out of the code when they do.

1. **Add an allow-list constant**, e.g. `CS2_ALLOWED_MODES = {"competitive"}`. Everything downstream
   reads it. A mode not on the list is never graded, never quoted, never counted.
2. **Classify the mode explicitly from the GC reply.** Do not infer it from a round count. The
   scoreboard message carries `max_rounds`, `team_scores`, `match_result` and `map` — enough to
   classify properly. Write the classifier as a pure function with its own tests, one per mode.
3. **A non-Competitive match in the chain is skipped, not graded.** It must not settle a wager, must
   not consume the window, and must not count as "a qualifying match" for the refund rule. It should
   still advance the chain cursor and still be stored — you want the data when modes come back.
4. **Verify the round floor is right for MR12.** The status doc records a floor of 16 rounds for
   "Premier/Competitive". CS2 Competitive is first-to-13, so a legitimate 13–2 win is 15 rounds and
   a 13–1 is 14 — **a floor of 16 would reject real matches.** Now that `match_result` and
   `team_scores` are available, express the guard as *"did this match reach a legitimate
   conclusion"* rather than a magic number. Report what the current code actually does before
   changing it.

**Two consequences to flag in `OPEN_QUESTIONS.md`, not to solve:**

- **CS Rating is a Premier concept.** Competitive uses per-map skill groups. The plan to condition
  the CS2 prior on CS Rating does not apply to a Competitive-only product. Say so; the prior work
  needs a different covariate.
- **Liquidity.** Competitive-only is a narrower funnel than Premier-only. Once the fill-rate
  instrumentation exists, this is the first thing to watch.

---

## B. Retire headshot %, and replace it with score-per-round

### B.1 Damage is not available. I checked; you should confirm.

Your status doc was right and I want the reasoning on record. Valve's published protobuf for
`CMsgGCCStrike15_v2_MatchmakingServerRoundStats` — the message the Game Coordinator returns when it
resolves a share code — contains:

```
kills, assists, deaths, scores, pings, mvps, enemy_kills, enemy_headshots,
enemy_2ks/3ks/4ks/5ks, enemy_kills_agg, team_scores, round_result, match_result,
match_duration, max_rounds, map, map_id, player_spawned, team_spawn_count, ...
```

**There is no damage field.** ADR would require downloading and parsing the demo file, which is a
different pipeline entirely. Damage is off the table.

**Verify this yourself against a real reply** — dump the full decoded message from one live GC
resolve and diff the field list against the above. My evidence is the public schema, not your
sidecar's actual response, and CS2 has diverged from CS:GO before.

### B.2 What to build instead: `cs2_score_per_round`

`scores` (repeated int32) *is* in the reply — the in-game score, driven by kills, assists and
objective play. Divided by rounds played it is a **rate**, which is the best-behaved metric family,
and it is the strongest candidate available. Simulated at 400,000 matches:

| Metric | easy | medium | hard | Verdict |
| --- | --- | --- | --- | --- |
| Headshot % (today) | 0.97× | 0.97× | 1.01× | calibrated on average, **exploitable** |
| Kills | 1.01× | 1.07× | 1.18× | drifts at hard |
| Kills per round | 0.91× | 0.97× | 1.07× | good |
| **Score per round** | **0.96×** | **0.99×** | **1.04×** | **best of everything tested** |

And it is structurally exploit-resistant, which headshot % is not:

| Engagements per match (true skill held constant) | Clears a 60% headshot bar | Clears the score/round hard bar |
| --- | --- | --- |
| 16.6 (normal) | 58.6% | 6.2% |
| 9.8 | 58.3% | 0.0% |
| 5.8 | 58.2% | 0.0% |
| 2.9 | 56.6% | 0.0% |

The reason is the denominator. Headshot % divides by *your kills*, which you control and can drive
to 2. Score-per-round divides by *rounds played*, which the match format floors at 13. **A player
who disengages moves this metric against themselves.** That is the property to preserve if you ever
design another market.

### B.3 Implementation

1. **Persist what the metric needs.** `cs2_matches` needs `score`, `rounds_played` and `max_rounds`
   from the reply. Derive `rounds_played` from `team_scores` and cross-check against `max_rounds`;
   store both and store the raw payload as you already do.
2. **Register `cs2_score_per_round`.** Increment `0.05` (a score-per-round σ is around 0.58, so 0.05
   is worth ~1.5pp of clear probability — inside the ≤2pp assertion you already have). Family: rate.
   Normal or Student-t placement is fine; skew is only +0.32.
3. **Retire `cs2_headshot_pct`.** Follow the migration-0024 precedent exactly: **refuse to run if any
   headshot contest is in flight**, rather than stranding entries in escrow. Remove it from
   `METRIC_BAR_INCREMENT`, from the registry and from the UI, and let the orphan-market test you
   already wrote catch anything you miss.
4. **Retire `cs2_kd_ratio` too? No — see workstream C.** K/D stays, it gets fixed.
5. **You have no CS2 data to migrate.** `last_code_at` is null and no match has ever been collected,
   so there is no backfill and no historical model to convert. This whole workstream is far cheaper
   now than it will ever be again — which is an argument for doing it properly rather than quickly.

**Verify the score composition empirically before you trust the model.** My simulation assumes
score ≈ 2×kills + assists + 2×objectives. Once you have real matches, regress actual `scores`
against actual kills/assists and record what you find. If the composition is materially different,
the prior needs refitting — the *metric* is still right, the *starting estimate* would not be.

---

## C. Fix the ratio metrics — K/D and Dota 2 KDA

Advertised 35%, delivering 25% and 20%. Cause: both are ratios with a long right tail, which drags
the mean and the spread up, so `μ + k·σ` lands where almost nobody goes.

### C.1 The fix: a blended quantile

Neither the lognormal nor the player's own percentiles wins alone. The lognormal is stable but
biased; the empirical quantile is well-centred but noisy at 27 effective samples. Blend them,
weighted by how much data actually supports the tail you are pricing:

```
p        = tier target (0.35 / 0.20 / 0.10)
n_eff    = (Σw)² / Σw²                      # the EWMA effective sample size, ~27
n_tail   = n_eff × p                        # how many of your matches inform THIS tail
a        = n_tail / (n_tail + W_PRIOR)      # W_PRIOR = 5.0 to start

emp      = EWMA-weighted empirical quantile of your history at (1 − p)
ln_bar   = exp( m + t_{n_eff−1}(1−p) · s · sqrt(1 + 1/n_eff) )
           where m, s are the EWMA mean and sd of log(value)

bar      = round_to_increment( a · emp + (1 − a) · ln_bar )
```

At hard, `a ≈ 0.35` — mostly the fitted curve, because 27 matches contain about 2.7 observations in
the top decile. At easy, `a ≈ 0.66` — mostly the player's own record. That is exactly the right
behaviour and it falls out of the formula rather than being tuned in.

### C.2 Measured, 3,000 simulated players each

| | easy | medium | hard |
| --- | --- | --- | --- |
| **CS2 K/D** — today | 0.79× | 0.86× | 1.09× |
| **CS2 K/D** — blended | **0.99×** | **0.98×** | **0.97×** |
| **Dota KDA** — today | 0.65× | 0.71× | 0.96× |
| **Dota KDA** — blended | **0.97×** | **1.00×** | **1.07×** |

The blend also has the *lowest* per-player spread of any method at the hard tier — better centred
*and* more stable than either component alone.

### C.3 Notes

- **`W_PRIOR = 5.0` is a starting point, not an answer.** Tune it against real history using the
  golden harness, optimising **mean absolute calibration error**, not just the mean — a rule that is
  centred on average but wrong per player is not fixed. Sensitivity: 3.0 centres better, 12.0 is
  more stable. Make it a per-metric constant.
- **Guard the log.** Values ≤ 0 break `log`. K/D with zero deaths is already special-cased; make
  sure whatever that produces is finite and positive before it reaches the estimator, and test the
  zero-death and zero-kill paths explicitly.
- **The weighted empirical quantile needs its own tests.** Weighted order statistics with linear
  interpolation are easy to get subtly wrong. Test against an unweighted `numpy.quantile` when all
  weights are equal, and against a hand-computed case with known weights.
- Consider whether `chess_moves` should move to the same blended estimator. Its lognormal was fitted
  properly on 4,647 games so it is probably fine — check, don't assume.

---

## D. The personal-bar escape hatch

**Full spec in `HYBRID_BRIEF.md`.** Summary so this document stands alone:

```
d = (room_bar − your_bar) / your_sigma
|d| ≤ ε   → graded on the room bar   (unchanged; ~85% of members)
|d| > ε   → graded on YOUR bar        (exactly the tier target, by construction)
            ...but only if your baseline is stable   ← the gate, load-bearing
```

**Do not change the room-bar formula. Do not change the composition predicate.** Both stay exactly
as they are — that is what makes this liquidity-neutral, and it is verifiable: rooms formed goes
92.1% → 92.0%.

Key numbers: Ana 5.09% → 10.16%, rooms worse than 2× fall 15.1% → 2.7%, room average clear rate
stays at 10.1% so the payout multiplier needs no compensating change, 14.9% of members affected.

**ε is per metric** (start 0.20) and belongs next to `METRIC_BAR_INCREMENT`. Assert that one bar
increment is smaller than ε, or the metric is mis-parameterised.

**The gate defaults to ineligible.** An honest player wrongly excluded gets today's behaviour; a
tanker wrongly included gets the hatch. That asymmetry is the entire safety argument, so make it
explicit in the code and in a test.

**Freeze the graded bar** into the contest record alongside the room bar. Settlement reads it; it
never recomputes.

**Card copy is in `HYBRID_BRIEF.md` §3.** Do not publish ε on the card — disclose the guarantee
("your chance stays near the tier's target"), not the mechanism.

---

## E. Write it up as you go

`WHAT_CHANGED.md` is a deliverable, not an afterthought, and the audience is **someone smart who is
not a statistician and did not write the code.** Keep the register of the existing file — it is
working. Add a section per workstream, each answering five questions in this order:

1. **What was wrong** — one sentence, no jargon.
2. **What a player actually experienced** — one sentence. "A bar advertised as 35% was cleared 25% of
   the time" beats "the estimator was biased in the upper tail."
3. **What we changed** — in plain terms first. If a formula helps, put it after the plain version,
   and define every symbol in the same sentence you first use it.
4. **How it was implemented** — which files, which new tests, what a reviewer should look at first.
   This is the part the current file is thinnest on and the part I most want.
5. **How we know it worked** — the before/after number, and the test that would fail if it regressed.

Specific things to explain properly because they will be asked:

- **Why damage was impossible** and score-per-round chosen instead — including the denominator
  argument, which is the generalisable lesson.
- **Why some players get their own bar** — frame it as protection, not exclusion.
- **Why the ratio metrics were unfair in the direction that cost players money**, and why that is
  different in kind from the exploits, which cost the platform money.
- **What "blended quantile" means** in one plain sentence. Something like: *"where you have enough
  games we use your own record; where you don't we lean on the shape we expect, and we slide between
  the two automatically."*

Also update: `OPEN_QUESTIONS.md` (the CS Rating and liquidity consequences from A, the score
composition regression from B, the `W_PRIOR` tuning from C), and `AUDIT_FINDINGS.md` if the
mode-classification or round-floor work turns up anything.

---

## Definition of done

- [ ] Full suite green, more tests than before, `alembic check` clean
- [ ] Golden file updated — every moved number explained in its commit message
- [ ] Model versioning in place; in-flight contests settle under the maths they were quoted
- [ ] Non-Competitive CS2 matches are skipped, not graded, and do not consume a window
- [ ] Headshot % retired with a migration that refuses to strand in-flight contests
- [ ] `cs2_score_per_round` live, with rounds-played persisted and the classifier tested per mode
- [ ] Ratio metrics blended; calibration measured before and after, per tier
- [ ] Escape hatch live behind versioning; rooms-formed rate confirmed unchanged
- [ ] `WHAT_CHANGED.md`, `OPEN_QUESTIONS.md`, `AUDIT_FINDINGS.md` current
- [ ] No production system touched

---

## Standing reminders

Where my numbers disagree with your golden harness, **the harness wins** — my population is
synthetic (μ ~ N(15,3), σ ~ Gamma(5.5)) and yours is real. Re-fit before finalising ε, `W_PRIOR`, or
the score-per-round increment, and report the fitted population.

Keep flagging where this brief is wrong. You have been right every time so far.
