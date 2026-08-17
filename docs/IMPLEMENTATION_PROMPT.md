# Implementation Brief — Money Match production-hardening pass

**Paste this whole file to Claude in the Money Match repo.** Attach `MONEYMATCH_RESEARCH.md`
and `IMPLEMENTATION_STATUS.md` alongside it.

---

## Who you are and what you're doing

You are working on **Money Match**, a peer-funded skill-wagering platform (FastAPI + Postgres +
Alembic on the backend, React + Vite on the web). A player links a game account, joins a
contest, plays a real match on the real game, and the platform grades the result from the game's
own data and moves money between players' wallets minus a rake. Currency is currently `DEMO`
play money; the team is preparing to launch with real users.

Two documents describe the current state:

- `IMPLEMENTATION_STATUS.md` — an honest account of what the code does today, including a
  known-issues list and a documentation-discrepancy list.
- `MONEYMATCH_RESEARCH.md` — an external research pass that quantified a set of defects in the
  bar-setting mathematics, matchmaking, liquidity and anti-abuse design. Every number in it is
  reproducible via the `analysis.py` script delivered with it.

**Your job has three parts:**

1. **Fix** the defects listed in Phases 1–5 below, in order, testing as you go.
2. **Audit** the codebase independently (Phase 6) for further production risks the research did
   not find — especially in matchmaking, settlement, concurrency and money handling.
3. **Explain** everything you did in a new plain-English markdown file (Phase 7) written for a
   non-specialist reader.

**Out of scope for this pass — do not do these:**

- Do not add new games or new game adapters. The four existing adapters (CS2, chess, Dota 2,
  PUBG) are what we're making correct.
- Do not add new markets/metrics *except* where explicitly instructed (the CS2 mode split in
  Phase 2.1 and the optional per-round metric in Phase 2.6).
- Do not build payments, KYC providers, or geolocation vendors. Where those seams exist, make
  sure they still fail closed; do not wire in a live provider.
- Do not implement house-guaranteed pots. The peer-funded structure is deliberate and
  load-bearing.
- Do not delete `test_opponents.py` yet — but see Phase 5.4.
- Do not make legal judgements. If you find something with legal implications, **flag it in
  writing, do not decide it.**

---

## Ground rules — these are non-negotiable

**1. Test as you go. Never batch fixes and test at the end.**

For every single change, in this order:

```
a. Write a test that FAILS against current behaviour and captures the correct behaviour.
   (For behaviour-preserving refactors, write a characterisation test that PASSES first,
    so you can prove you didn't change anything.)
b. Make the smallest change that turns it green.
c. Run the FULL test suite, not just your new test.
d. Only then move to the next item.
```

If a change makes an unrelated test fail, **stop and understand why before touching that test.**
A failing pre-existing test is information. Do not "fix" it by editing the assertion unless you
can explain, in the commit message, exactly why the old assertion encoded wrong behaviour.

**2. One logical change per commit.** Commit message format:

```
<area>: <what changed>

Why: <the defect, with the number from MONEYMATCH_RESEARCH.md if applicable>
Risk: <what could break>
Verified by: <test names>
```

**3. The money path is sacred.** `Split.__post_init__` asserts `sum(payouts) + rake == pot`.
Per-contest reconciliation is `entries == distributed + rake + still_held`. Global is
`sum(available + escrow) == promo funding − rake`. **These invariants may not be weakened,
relaxed, or made conditional under any circumstance.** If a change you want to make appears to
require relaxing one, that means the change is wrong. Integer cents only — no floats anywhere in
the money path.

**4. Every behavioural change to bar mathematics must be versioned.** See Phase 2.0. In-flight
contests were priced under the old math and must settle under the old math. Getting this wrong
means a player is graded against a bar that was never quoted to them, which is both a
correctness bug and a consumer-protection problem.

**5. Fail closed, always.** Any new flag, gate, or guard defaults to the safe state. If a
dependency is unavailable, refuse rather than allow. Where existing code fails open, that is a
bug — see Phase 1.1.

**6. Do not touch production.** Work locally against a test database. Anything that can only be
verified in production goes into a manual runbook you hand to the team (Phase 5.5). Do not run
migrations against the deployed database, do not flip live feature flags, do not call the
deployed API with mutating requests.

**7. When you're uncertain, write it down instead of guessing.** Keep a running
`OPEN_QUESTIONS.md` as you work. Anything where you had to assume something about intent,
anything you found that's out of scope, anything that smells wrong but you can't prove — it goes
in there. That file is a deliverable.

---

## Phase 0 — Baseline and safety net (do this first, no exceptions)

You cannot know whether you broke something if you don't know what worked when you started.

**0.1 Establish the baseline.**

- Run the full API suite (93 test files, ~657 test functions, ~1,028 collected with
  parametrisation) and the web suite (30 vitest files, 4 Playwright specs). Record exact pass/
  fail/skip counts and total runtime in `OPEN_QUESTIONS.md`. `IMPLEMENTATION_STATUS.md` §16
  admits the suite was not re-run when that document was written — so **assume nothing about it
  being green.** If anything is already failing, document it before you change a line.
- Run `alembic check`. Confirm 24 migrations, head `0024_retire_cs2_faceit`.
- Record current test coverage on the modules you're about to touch: `fairness.py`,
  `skill_prior.py`, `metric_models_service.py`, `pool_engine.py`, `grading.py`, the settlement
  worker, `cs2_prior.py`, `cs2_submission.py`, `cs2_chain.py`, `linking_service.py`.

**0.2 Build the golden-snapshot harness before changing any math.**

`IMPLEMENTATION_STATUS.md` §5 claims an "audit replay guarantee" — every number a player sees
re-derives byte-for-byte from the saved snapshot. **Verify that claim is machine-checked. If it
isn't, make it so now**, because it's your regression net for all of Phase 2.

Build a test that, for a fixed corpus of synthetic and (if available) real player histories,
records for each `(game, metric, difficulty)`: `μ, σ, σ_effective, n, n_eff, bar, p_quoted,
room_bar, multiplier`. Freeze the output as a golden file. Any Phase 2 change that moves a number
must move it *in the golden file, deliberately, with the diff reviewed in the commit.*

Seed the corpus with the worked examples in `IMPLEMENTATION_STATUS.md` §5.4, which are known to
match deployed behaviour exactly:

| Case | Expected easy / medium / hard |
| --- | --- |
| CS2 K/D, private stats, prior μ=1.00 σ=0.25 | 1.10 / 1.20 / 1.30 |
| CS2 K/D, public stats, lifetime K/D 0.606 | 0.70 / 0.80 / 0.95 |
| CS2 kills, μ=10.92 σ=6 | 13 / 16 / 19 |
| CS2 headshot %, μ=42.34 σ=12 | 47 / 52 / 58 |

**0.3 Add a property-based invariant test for the money path.** Use `hypothesis`. Generate
arbitrary pots, rake basis points, winner counts and weight vectors; assert
`sum(payouts) + rake == pot` and `all(isinstance(x, int) for x in payouts)` always. Include
adversarial cases: 1 winner, N winners, zero winners, pot smaller than the winner count, rake
0 bps, rake 10000 bps, weighted splits with ties. This test should never be deleted.

**0.4 Add a "no floats in the money path" test.** Static check (AST walk or grep-with-teeth) over
the money modules asserting no float literals, no `/` on money quantities, no `float()` calls.

---

## Phase 1 — Stop the bleeding

These are small, high-severity, and mostly independent. Do them all before Phase 2.

**1.1 The geo-fence fails open. Fix it.**

`excluded_states` reads an empty feature flag and fails **open** — on a fresh database every
state is allowed. The code comment claims it fails closed. It does not.

- Make `assert_can_enter` refuse when the excluded-state config is empty, missing, malformed, or
  unreadable. Empty config is not "no exclusions," it is "configuration missing → block."
- Add a startup assertion: in `ENV=prod`, refuse to boot if the excluded-state list is empty or
  does not contain all 14 seeded states (AZ, AR, CT, DE, FL, IN, LA, MD, MN, MT, SC, SD, TN, WY).
- Tests: fresh DB blocks all 14; empty flag blocks everything; malformed flag blocks everything;
  a null `residence_state` blocks; each of the 14 states blocks individually; a permitted state
  passes.
- Fix the lying comment.

**1.2 Grading semantics: `>=` vs `>` must be explicit, consistent, and disclosed.**

Kills and `chess_moves` are integers. On a discrete metric with μ=17, σ=6, a hard bar of 25 has
`P(X ≥ 25) = 11.1%` but `P(X > 25) = 8.8%` — a 27% relative difference decided entirely by one
character in the grading code.

- Find the comparison operator in `grading.py` for every stat market. Write down what each one
  currently is.
- Introduce an explicit `comparison_op` on the market definition (`">="` or `">"`). Do not
  infer it.
- Make `clear_prob` use the *same* operator. On a continuous metric this is a no-op; on a
  discrete one it is not.
- Surface it in the card copy: "**25 or more** kills," not "25 kills."
- Tests: for each market, a boundary case where the realised value exactly equals the bar. That
  test is the whole point.

**1.3 The CS2 prior is wiped on link refresh.**

Only the Steam OpenID callback calls `cs2_prior.seed()` (n=3). Both `linking_service.bind()` and
`linking_service.refresh()` call `metric_models_service.bootstrap()`, which rebuilds from
*stored* matches — of which there are zero — writing n=0. The metric then reads provisional and
Solo Pools shows "No pools on this game yet."

- Make `bootstrap()` non-destructive when it has nothing to bootstrap *from*: if the stored
  match count is below the point where an empirical model beats the prior, keep the prior rather
  than overwriting with n=0.
- Better: make the seeded prior and the empirical model separate concerns that blend, rather
  than one clobbering the other. `skill_prior.shrink()` already exists for exactly this — the
  bug is that `bootstrap()` bypasses it.
- Tests: bind → refresh → assert model still non-provisional; bind → 0 stored matches → refresh
  → assert bar is still quotable; bind → 40 stored matches → refresh → assert the empirical
  model now dominates the prior.

**1.4 `_derived()` ignores data Steam already returns.**

`_derived(kd)` scales generic headshot%/kills defaults by the K/D ratio while ignoring
`total_kills_headshot` and `total_matches_played`, which arrive in the same
`GetUserStatsForGame` response. For a real test account (K/D 0.606, actual HS% 36.6, actual 8.19
kills/match) it seeds HS% 42.3 and kills 10.9 — quoting easy bars of 47% and 13 kills to a
player whose real form is 36.6% and 8.19 kills. That player never clears, loses four contests,
and churns.

- Compute directly from the returned totals where they exist: `hs_pct = total_kills_headshot /
  total_kills`, `kills_per_match = total_kills / total_matches_played`. Fall back to the derived
  heuristic only when the fields are absent.
- Handle the documented 400 case: `GetUserStatsForGame` returns 400 unless Steam *Game details*
  are public, which is the **normal** path, not the edge case. Both branches need tests.
- Test with the real test account's numbers and assert the seeded μ matches actual form within a
  tight tolerance.

**1.5 The sidecar health response is ambiguous by design. Make it unambiguous.**

`gc_client.health()` never raises and returns the same shape whether the sidecar is
up-but-unattached or entirely unreachable; the router then discards the `detail` field that
would distinguish them. This is why `ready:false` has persisted for days without anyone knowing
which failure it is.

- Return a discriminated status: `attached` / `up_but_unattached` / `unreachable` /
  `circuit_open`, each with `detail` preserved end to end.
- Surface it in `/health` and the admin view.
- Tests: mock each failure mode and assert the four statuses are distinguishable.

**1.6 Documentation discrepancies (§15 of `IMPLEMENTATION_STATUS.md`).**

These mislead anyone reading the source, including you and including a diligence reviewer.

- `fairness.py` module docstring states `k = {easy: 0.5, medium: 1.0, hard: 1.75}` with clear
  rates ≈31/16/4%. The code reads `POOL_DIFFICULTY_K` = `{0.385, 0.842, 1.282}` → 35/20/10%.
  Fix the docstring. Then add a test that asserts the docstring's stated values match the
  constants, so it can never drift again (parse it, or assert against a single source of truth).
- `METRIC_BAR_INCREMENT` still contains `cs2_adr`, retired in migration 0024. Remove it. Add a
  test that every key in `METRIC_BAR_INCREMENT` is a live registered market.
- `skill_prior`'s docstring describes shrinkage as general; `_PRIORS` is empty so it applies to
  `chess_moves` alone. Fix the docstring to say so.
- `docs/game/cs2-steam.md` says the GC sidecar "is not in the repo." It is — `gc-sidecar/` with
  `server.js`, `supervise.js`, `get-token.js` and a Dockerfile. Fix.

---

## Phase 2 — Bar-setting mathematics

**Read `MONEYMATCH_RESEARCH.md` §2 in full before starting this phase.** Run its `analysis.py` so
you have the numbers in front of you.

**2.0 Versioning — do this before any math change.**

Every bar-setting change alters numbers players were quoted. Therefore:

- Add `model_version` (integer or semver string) to the frozen `baseline_snapshot` on
  `queue_tickets` and to whatever the pool/match rows persist.
- Grading and settlement must read the model version from the snapshot and apply *that* version's
  math. Keep old versions as pure functions; do not delete them.
- Add a test: freeze a snapshot under v1, bump to v2, settle, assert the v1 math was used.
- Add a migration for the column. Follow the `0024` precedent of **refusing to run** if it would
  strand in-flight contests, and write the same style of guard.

**2.1 Split CS2 game modes. This is the largest live correctness bug.**

Premier (5v5, first to 13), Competitive (5v5, first to 16) and Wingman (2v2, first to 9) appear
to share one `cs2_kills` model. Kills in those modes are not the same random variable. Pooling
them makes a bar quoted at 10% clear **23.2%** of the time for a player who queues Premier — a
**2.35×** mispricing they select freely after the bar is set.

- **First: verify it.** Confirm whether the three modes actually share a model. If they don't,
  say so in `OPEN_QUESTIONS.md` and skip to 2.2. Do not assume the research is right.
- Key `metric_models` by mode: `user × game × mode × metric`. The migration must backfill
  existing rows sensibly (probably: mark them provisional rather than guess a mode).
- Make the wager **bind** to a mode. A Premier wager grades only against Premier matches. A
  non-matching match in the chain is **skipped, not graded** — it must not consume the wager and
  must not be treated as a qualifying match.
- The GC scoreboard reply carries enough to classify the mode; your existing round floors (16
  Premier/Competitive, 9 Wingman) prove you already have the discriminator. Make mode
  classification explicit and tested, not implied by a floor.
- Consider the TrueSkill 2 structure for the prior: `skill_mode = w_mode · base_skill +
  offset_mode`, so a player's Wingman history still informs their Premier model instead of
  fragmenting their data into three thin buckets. (Reference: `MONEYMATCH_RESEARCH.md` §2.9.)
- Tests: a Wingman match in the chain does not settle a Premier wager; a Premier match does; a
  player with only Wingman history is provisional on Premier; mode classification is correct for
  each mode's round counts including overtime.

**2.2 Close the headshot-percentage exploit. Do this before any real money moves.**

Headshot % is `headshots ÷ kills`. Its variance is `p(1−p)/K`, and **the player controls K.** A
60% bar priced at 5% for a normal 17-kill game clears **51%** of the time for a player who takes
4 kills with a Deagle/AWP. No tooling, no collusion, no need to win the round.

Measured clear rates at a 60% bar:

| Behaviour | P(clear) |
| --- | --- |
| Normal 17-kill game, 42% aim | 5.0% |
| 4 kills, 42% aim | 20.3% |
| 4 kills, headshot-weapon play (62%) | **51.0%** |

- **Required:** add a **kill floor** to headshot-% markets. Only matches with ≥ 12 kills grade a
  headshot wager; below that the match is skipped like an off-mode match. This is the same class
  of rule as your existing round floor, it fits the architecture, and it collapses the exploit by
  shrinking the variance term ~3×. Disclose it on the card: "counts on games where you get 12+
  kills."
- **Also required:** model headshot % on a **beta-binomial** predictive rather than a normal, so
  the quoted clear probability reflects the actual kill count distribution. Place the bar on the
  predictive distribution of `H/K` marginalised over `K`. Note this *prices* the exploit; the
  kill floor *removes* it. Do both.
- **Consider:** a `cs2_headshots_per_round` market as the long-term replacement, which converts a
  ratio with a controllable denominator into a count with a fixed observable one.
- Tests: a 4-kill match does not grade a headshot wager; a 12-kill match does; the beta-binomial
  clear probability matches a Monte-Carlo simulation within tolerance; the low-kill-count clear
  rate is no longer 3× the high-kill-count one.

**2.3 Replace the plug-in normal with a Student-t predictive.**

Bars are placed at `μ̂ + k·σ̂` using point estimates from an EWMA whose **effective sample size is
27.1**, not 50 (`n_eff = (Σw)²/Σw²` for n=50, half-life 10). Ignoring that σ̂ is itself estimated
biases every hard bar: with a true process of *exactly* N(17, 5.5), the realised clear rate is
**11.6%** against a quoted 10% — a 16% relative error straight out of the pot math and the
multiplier.

```python
n_eff = w.sum()**2 / (w**2).sum()
sigma_unbiased = sigma_hat * sqrt(n_eff / (n_eff - 1))
t_q = student_t.ppf(1 - p_target, df=max(n_eff - 1, 2))
bar = round_to_increment(mu_hat + t_q * sigma_unbiased * sqrt(1 + 1/n_eff))
```

| Difficulty | Target | Plug-in normal (today) | Student-t predictive |
| --- | --- | --- | --- |
| Easy | 35.0% | 35.8% | **35.0%** |
| Medium | 20.0% | 21.3% | **19.9%** |
| Hard | 10.0% | 11.6% | **10.0%** |

- Apply the *same* distribution to `clear_prob` as to `personal_bar`. `IMPLEMENTATION_STATUS.md`
  §5.5 is right that placing a bar under one distribution and judging it under another is two
  different answers to the same question — extend that rule to the t.
- Keep `effective_sigma` as a guard rail but expect it to stop binding for most players; the
  t-predictive addresses its underlying motivation properly.
- Return `n_eff` from `compute_ewma` so callers stop recomputing it.
- Tests: Monte-Carlo over ≥4,000 simulated players confirms the realised clear rate is within
  0.5pp of target at all three difficulties; `n_eff` is correct for known windows (n=20/hl=10 →
  17.3; n=50/hl=10 → 27.1; n=50/hl=20 → 40.4); the golden file diff is reviewed and intentional.

**2.4 Negative binomial for kills.**

Kills is an overdispersed count (index ≈ 2.12), not a symmetric normal. Add `cs2_kills` (and
mode variants) to a per-metric distribution registry alongside the existing
`METRIC_POSITIVE_SUPPORT` lognormal branch. Fit `r` and `p` from `μ̂` and `σ̂²` by moment
matching, guarding the `σ² ≤ μ` case (fall back to Poisson).

This is worth ~22% relative at hard — real, but **do 1.2 first**, because the `>=`/`>` fix is
worth 27% and takes five minutes.

**2.5 Bar increments.**

One increment of bar movement is worth this much clear probability:

| Metric | Increment | At easy | Rounding error alone |
| --- | --- | --- | --- |
| `cs2_kd_ratio` | 0.05 | **7.41pp** | **±3.70pp** |
| `cs2_kills` | 1.0 | 6.74pp | ±3.37pp |
| `cs2_headshot_pct` | 1.0 | 3.09pp | ±1.54pp |

A K/D bar quoted at "35%" is somewhere between 31.3% and 38.7% from rounding alone — larger than
the negative-binomial correction.

- Change `METRIC_BAR_INCREMENT['cs2_kd_ratio']` from `0.05` to `0.01`. CS2 displays K/D to two
  decimals everywhere; nobody will notice except the calibration curve.
- Audit every other increment the same way: compute `φ(k)/σ · increment` for a representative σ
  and assert it's under ~2pp. Add that as a test so new markets can't ship with a coarse
  increment.

**2.6 Decouple the μ and σ half-lives; widen the σ window.**

Form drifts. Volatility doesn't. There is no reason to estimate both on the same window.

| hl_μ | hl_σ | window | MAE vs target |
| --- | --- | --- | --- |
| 10 | 10 | 50 | 4.32pp |
| 10 | 30 | 50 | 4.05pp |
| **10** | **30** | **100** | **3.80pp** |

- Make the half-lives independently configurable; default `hl_μ = 10`, `hl_σ = 30`, bootstrap
  window 100 (up from 50 — check adapter rate limits before raising the fetch).
- **Note the interaction with 4.2:** asymmetric updating changes `hl_μ` directionally. Implement
  2.6 first, then 4.2 on top of it, and re-run the golden file after each.

**2.7 Optional if time allows: per-round metrics.**

The research is *sceptical* that round-normalisation reduces variance — round count is only 19%
of kills variance, and because stomps are short-and-high-kpr while grinds are long-and-low-kpr,
the two partially cancel, so a per-round metric can be *wider* than a total. Do not do this for
variance reduction.

Do it, if at all, for **cross-mode comparability** (it lets one prior serve Premier and Wingman,
per 2.1) and for **dispute defensibility** ("19 kills but the game was 13-3" is a real complaint
you will receive).

**Before deciding: measure the actual correlation between round count and kills-per-round on
your own data.** That's a two-line query — once you have collected a single CS2 match, which per
Phase 5 you haven't. If you can't measure it, don't ship it; write the query and put it in the
runbook.

**2.8 A real CS2 prior conditioned on CS Rating.**

`_PRIORS` is an empty dict; `prior_for()` returns a value only for `chess_moves`; `shrink()` with
`prior=None` returns `(μ, σ)` unchanged. So shrinkage is inert outside chess. `host_rating()`
compounds this by reading `formats`/`primary_speed` from a chess-shaped profile snapshot, so it
returns `None` for CS2 regardless.

- Fix `host_rating()` to return CS Rating for CS2.
- Fit `μ_metric = a + b · rating` from public data, exactly the way `mean_moves(elo) = 16.65 +
  0.01013·elo` was fitted for chess (4,647 games — the most rigorous modelling in the codebase;
  copy its method and its honesty about limitations). Roughly 500 rated players' histories are
  enough, and **you can gather them without a single wager being placed.**
- Populate `_PRIORS` for the CS2 metrics.
- Write up the fit the same way the chess prior is written up: sample size, date, bands, residual
  spread, and where the fit is held flat outside the sampled range.

---

## Phase 3 — Matchmaking and liquidity

**3.1 Instrument the market before changing it.** You cannot tune what you can't see, and the
practice opponents currently hide the only metric that matters.

Add, with demo/bot users excluded, bucketed by `game × metric × difficulty × entry`:

- `fill_rate` = rooms formed / tickets enqueued
- `time_to_fill` histogram (p50, p90, p99)
- `expired_unmatched` count and rate
- `composition_reject_rate`, split by *which* predicate rejected (band vs spread cap vs
  `can_pair`) — this tells you whether your fill problem is thickness or over-strict predicates
- `settlement_success_rate` and `% refunded for no qualifying match`

Expose as an admin view with one row per bucket. Ship this before 3.2 so you can measure the
effect of 3.2.

**3.2 Collapse the entry dimension with pro-rated payouts.**

108 buckets (4 games × 3 metrics × 3 difficulties × 3 entry tiers) at 200 joins/day gives a
**23.7% fill rate with a 51.8-hour expected wait**. Twelve buckets gives **99.8% at 5.8 hours**.

- Match on `metric × difficulty`; let entry float within the existing $1–$100 band.
- Payout among clearers: `payout_i = distributable × entry_i / Σ_{clearers} entry_j`, integer
  cents, remainder to rake — the existing `Split` invariant handles this unchanged.
- Tests: mixed-entry pool reconciles exactly; a $1 entrant and a $100 entrant in the same pot
  both settle correctly; single clearer takes the whole distributable; zero clearers refunds all.

**3.3 Weighted-payout difficulty collapse — design first, then decide.**

The bigger win is making difficulty a *personal* attribute rather than a bucket key:

```
weight_i = 1 / p_target_i           # easy 2.86, medium 5.0, hard 10.0
payout_i = distributable × weight_i·entry_i / Σ_{clearers} weight_j·entry_j
```

Expected weighted claim is equalised across tiers by construction, the pot stays peer-funded, and
B drops by another 3×.

**But this removes a safeguard.** Today `composition_ok` requires every member's implied clear
probability against the *shared room bar* to sit in `[p_target/2, min(2·p_target, 0.5)]` — the
anti-shark rule in both directions. With personal bars and weighted payouts there is no shared
bar to drag, which is cleaner in one way and unguarded in another.

**Do not ship this blind.** Write a simulation first: N players with heterogeneous (μ, σ),
mixed difficulty tiers, weighted payouts. Measure whether any (μ, σ) profile earns systematic
positive EV against the field. If one does, the weighting is wrong or needs a cap. Put the
simulation in the repo as a permanent tool, not a scratch file. Only implement if the simulation
is clean; otherwise document the finding and stop.

**3.4 Widen the fill window, shorten the play window.**

Today one 24-hour window does two jobs that pull in opposite directions: a long window helps
liquidity and is exactly what makes the free option valuable (Phase 4.1). Separate them:

```
Phase FILL:  ticket waits in queue up to 24h. No escrow. Bar frozen at enqueue.
Phase LOCK:  room forms -> push notification -> ~10 min accept window -> escrow
Phase PLAY:  ~45-60 min to start a qualifying match. Expire -> full refund, zero rake.
```

This keeps the liquidity benefit of a long wait, removes ~80% of the option value, and cuts
time-to-settlement from 24 hours to under an hour — which is what makes the end-to-end demo
filmable.

- Requires a real accept/ready-check state on the ticket, push delivery, and careful state-machine
  work. **Take this slowly and test the state machine exhaustively**, including: accept after
  expiry, double-accept, accept-then-crash, all-accept, partial-accept (what happens to the
  players who did accept? They must be refunded or re-queued, never stranded in escrow).
- The existing `MATCH_CONFIRM_TTL_SECONDS` H2H confirm flow is prior art in your own codebase —
  reuse its shape rather than inventing a second one.

**3.5 Keep greedy matching.** Do not replace `FOR UPDATE SKIP LOCKED` match-on-write with batch
matching. The published result is that neither policy dominates and both reach ~91% of optimal at
a sojourn period of 6; greedy converges faster and suits short sojourn times. Your problem is
market *thickness*, not matching *policy*, and no policy fixes an empty market. (Reference:
`MONEYMATCH_RESEARCH.md` §3.3.)

---

## Phase 4 — Anti-abuse economics

**4.1 Measure the free option before you try to close it.**

A player who warms up in Casual or Deathmatch (neither produces a share code, so both are
invisible to you), queues Premier only when sharp, and otherwise lets the window expire for a
full refund, achieves a clear rate **1.4×–1.9×** their modelled rate. In a four-handed $25 pool
that's **+32.8% ROI for the shark and −31.7% for the casual across from them**. A casual losing
31.7% per contest churns after four contests.

Phase 3.4's short play window is the structural fix. Add these two on top:

- **Calibrate against the completing population, not the modelled one.** If you set `k` so the
  realised clear rate *among players who actually play* is 35%, the selection effect is priced in
  automatically and the pot math becomes correct. You never have to detect or prove selection —
  you just measure the outcome. This falls straight out of Phase 5.1 and is the cheapest fix on
  this list.
- **Track completion rate as a first-class risk signal.** A player at 55% completion against a
  population at 85% is exercising the option whether or not deliberately. That's a `risk_flags`
  row and a candidate for a bar adjustment. Reuse the existing nightly derived-detector pass
  (`win_streak`, `pair_cap`).

**Do NOT grade a no-show as a loss.** "You cannot lose by not playing" is a genuinely good
consumer-protection property and is worth more in a regulatory conversation than the leakage
costs. Do not retain a fee on expiry either; prefer non-monetary friction (re-queue cooldown,
visible completion-rate badge, leaderboard exclusion below a threshold).

**4.2 Sandbagging is three matches, not ten.**

| Tanked matches | Hard bar | True clear rate | Edge |
| --- | --- | --- | --- |
| 0 | 21 | 10.0% | 1.0× |
| **3** | 20 | **29.3%** | **2.9×** |
| 10 | 17 | 50.0% | 5.0× |

Three deathmatch-quality Premier games — about 90 minutes — buys a 2.9× edge, because one bar
increment is worth 3.2pp of clear probability at hard.

- **Asymmetric updating.** Bars rise fast, fall slow: `hl_up = 10`, `hl_down = 40` in
  `compute_ewma`. Layer this on top of Phase 2.6's decoupled half-lives.
- **Bar velocity floor.** No personal bar may fall more than X% per rolling 7 days regardless of
  what the model says. Blunt, effective, trivially auditable. Pick X from simulation.
- **Verify the existing detector fires at n=3.** Your sandbagging z-test compares recent form
  against the older baseline. With σ=5.5 and three samples at 4 kills, `z = (4−17)/(5.5/√3) =
  −4.09`, which should fire comfortably. **If it doesn't, the threshold is too loose** — write
  the test that proves it either way.
- **Note the accidental safeguard you must not remove:** σ̂ *rises* while μ̂ falls under tanking
  (4.68 → 6.24), which partly offsets the bar drop. If you ever switch to a robust/trimmed σ
  estimator, that safeguard disappears. Leave a comment saying so.
- **Prior art:** US 9,349,249 B2 (Gamblit Gaming) claims outlier-test-based sandbagging detection,
  dynamic handicap adjustment, wager caps keyed to professed skill, and automatic upward ranking
  adjustment. **Read the claims before implementing handicap-adjustment or bet-limiting keyed to
  detected sandbagging** — those are the two closest — and flag any overlap for counsel. Do not
  make the call yourself.

**4.3 Party stacking.**

Stacking with better friends is a legitimate, currently-undetected way to move your average.
TrueSkill 2 found this empirically and added an explicit `squadOffset(squad size)` term, so treat
it as measurable fact, not theory.

- The GC scoreboard reply gives you the full roster, so this is a query over `cs2_matches`, not
  new plumbing.
- For each settled match compute `stack_size` = number of teammates appearing in ≥ 40% of the
  player's last 20 matches.
- Fit `μ_player + squadOffset(stack_size)`; place the bar at the player's *expected* stack size.
- A solo-queue player who suddenly five-stacks is a risk flag, not a ban.

**4.4 Multi-account collusion in pools.**

`can_pair` covers self-pair, same-host account, 24h re-pair and provisional metrics — for H2H.
Check pools separately:

- Pure self-dealing in a pool is self-limiting (you pay the rake to yourself), so it's not the
  threat. **The threat is 3 sandbagged accounts you control plus 1 real player**, where you
  extract from the stranger.
- At minimum: apply `can_pair`-equivalent checks across all pairs in a forming room (the docs say
  this already happens — verify it), and add a detector for rooms where multiple members share
  device/IP/payment fingerprints. Flag, don't auto-block, and route to the existing risk queue.

---

## Phase 5 — Observability, ops, and the calibration harness

**5.1 Build the calibration harness. This is the highest-value item in the phase.**

Nothing in the codebase compares predicted clear rates against realised ones. This one artifact
is simultaneously: your technical credibility, your pot-math correctness check, your free-option
detector (4.1), and evidence that skill predominates.

At bar placement, snapshot into an immutable `bar_predictions` table:

```
contest_id, user_id, game, mode, metric, difficulty, entry_bucket,
mu_hat, sigma_hat, sigma_effective, n_raw, n_eff, prior_used, prior_weight,
bar, p_predicted, distribution_family, positive_flag, comparison_op,
model_version, placed_at
```

At settlement, append: `realised_value, cleared, match_id, rounds_played, mode_actual,
kills_total, settled_at, outcome ∈ {cleared, missed, refunded_no_match, cancelled}`.

`model_version` matters more than it looks — without it you cannot distinguish a real calibration
improvement from a population shift.

Compute and expose:

- **Reliability diagram** — predicted vs realised by bin, with Wilson 95% intervals. This is
  *the* chart.
- **ECE** = `Σ_b (n_b/N)·|realised_b − predicted_b|`. One trendable number. Target under 3pp.
- **Brier score with the Murphy decomposition** (`reliability − resolution + uncertainty`).
  Report both terms — a well-calibrated model with zero resolution is one that always predicts
  the base rate, and you want to be able to prove you're not that.
- **Slices**: metric × difficulty × mode × `n_eff` bucket × prior-used. The aggregate can look
  calibrated while every slice is wrong (see 2.1) — the harness must not be able to hide that.
- **Completion-conditional calibration**: realised clear rate among completers, separately from
  the modelled population. That gap *is* the free-option value, measured.

Sample sizes: ~200 settled contests per cell catches a gross error, ~800 a meaningful one, so
~1,800 for a credible first curve and ~7,000 for a tight one.

**Because that's months of live traffic, build the backtest mode first:** run bar placement over
historical match sequences from public CS2 data and score it retrospectively. **You do not need a
single wager to produce a first calibration curve.** Make this a CLI tool in the repo.

**5.2 Alerting.** A stalled sidecar or a chain collecting nothing is currently invisible without
manually querying an endpoint. Page on:

- Worker heartbeat stale > 120s (the flag exists; wire it to an alert)
- Sidecar not `attached` for > 5 min (needs 1.5)
- Zero share codes collected in 6 hours across all users
- `settlement_paused` set (i.e. a `ReconciliationError` fired)
- Any reconciliation breach, per-contest or global
- Fill rate below threshold in any bucket for > 24h
- Adapter error rate / circuit breaker open

**5.3 Rate-limit budgets.** The Steam Web API Terms of Use cap you at **100,000 calls per day** —
about 69 chain syncs per minute across your entire user base, before resolving a single share
code. Add a global, persisted, per-provider call budget with backpressure, not just per-request
retry logic. Do the same for PUBG (throttled 9/min), OpenDota and Lichess. Alert at 70% of daily
budget.

**Note the circuit breaker is probably per-process** (3 failures → 30s stop). With multiple worker
copies that's N independent breakers, so the effective failure rate against the upstream is N×
what you think. Verify and, if so, move the breaker state to the database or Redis.

**5.4 The demo scaffolding.**

`test_opponents.py` is well-built — real wallets, real ledger rows, no special case in the money
path, `is_enabled()` keyed off `demo_mode.is_demo_user` rather than an environment flag, so a
real signup never sees a fabricated opponent in any environment. Don't delete it yet, but:

- Add a test asserting bots are excluded from **every** analytics surface, including the new
  Phase 3.1 metrics. If a bot ever lands in the fill-rate numerator, that metric is worthless.
- Add a `prod` startup assertion that zero demo users exist in the production database.
- `/api/v1/wallet/demo-deposit` **is** mounted in production. That's consistent only while every
  wallet is play money. Add a guard that refuses to mount it once a non-DEMO currency exists, so
  it cannot survive the switch by accident.

**5.5 The production runbook.** You cannot verify the CS2 pipeline end to end from a dev machine —
it needs a real Steam account, a real match authentication code, and a real Premier game. Write
`RUNBOOK.md` covering:

- Step-by-step first-real-settlement procedure (link Steam → create match auth code → name the
  starting cursor → play → observe chain sync → observe GC resolve → observe grade → observe
  payout), with the exact query or endpoint to check at each step and what "healthy" looks like.
- Sidecar fleet operation: how to add an account, rotate one out, and confirm attachment. **The
  research flags that a single Steam account is both a single point of failure and a
  terms-of-service exposure** (the Steam Subscriber Agreement prohibits Automation) — the
  architectural mitigation is N ≥ 3 accounts with no other Steam surface: no inventory, no
  trading, no friends, no purchases beyond CS2.
- What to do when: sidecar unattached, chain returns 412 / 403 / 429, settlement paused,
  reconciliation breach, adapter outage.
- Kill-switch procedure (`queue_paused`, `settlement_paused`) and what each one does to money in
  flight.

---

## Phase 6 — Independent audit: find what the research missed

The research pass looked at mathematics, economics and legal posture. **It did not read your
code.** This phase is you doing what it couldn't. Budget real time for it — a fresh critical read
of the matchmaking and settlement paths is likely to find things worth more than half of Phase 2.

Write findings to `AUDIT_FINDINGS.md` with: severity (P0 blocks launch / P1 fix before real money
/ P2 fix later), a concrete failure scenario with inputs, and a proposed fix. **Fix P0s in this
pass; propose P1s and P2s.**

Specific things to hunt for:

**Matchmaking correctness**

- **TOCTOU in room formation.** Docs say gather compatible tickets → derive room bar → check
  `composition_ok` → check `can_pair` → escrow atomically. Confirm the compatibility checks
  happen *inside* the `FOR UPDATE SKIP LOCKED` transaction, not before it. A check outside the
  lock is a race.
- **Rounding after composition check.** `room_bar` is the rounded mean of personal bars. Does the
  code re-verify `composition_ok` *after* rounding? Rounding can push a member out of band, which
  means a room can form that violates its own predicate.
- **Frozen snapshot vs. live model.** The baseline is frozen into `baseline_snapshot` at enqueue.
  Verify settlement grades against the **snapshot**, not a re-read of the live model, on every
  path — including the retry, resettle and dispute paths.
- **Starvation.** Can a player with unusual (μ, σ) never form a room? Is the pool widening ladder
  monotone and does it terminate? What's the worst-case wait, and does the UI tell the truth
  about it?
- **Room size 4 vs 3.** `POOL_ROOM_SIZE = 4`, `POOL_MIN_ROOM = 3`. Does the pot math, the
  multiplier cap (`min((1−rake)/p_target, room_size·(1−rake))`) and the composition band all use
  the *actual* room size rather than the nominal one?
- **H2H ladder.** Two tickets pair within the *wider* of their two ladders. Confirm the widening
  is monotone in age, that the "past the last stage" branch really stops auto-widening, and that
  an old ticket can't pair with someone wildly mismatched through ladder interaction.
- **Tournaments.** The dispersion cap uses μ only, not σ — can a low-μ/high-σ player be admitted
  to a field they dominate? "An entrant with no qualifying match ranks last" appears to conflict
  with the global rule "no qualifying match ⇒ full refund, zero rake." Which wins? Is the
  tie-break "earlier enqueue" gameable, and are enqueue timestamps unique and monotonic?

**Settlement and money**

- **Payout idempotency.** The unique index on `share_code` prevents CS2 replay. What prevents
  *payout* replay if the worker crashes after writing ledger rows but before updating contest
  status? Each unit of work runs in its own transaction and rows are re-claimable — trace whether
  re-claiming a partially-settled contest can double-pay. Write the test that proves it can't.
- **Concurrency cap release.** Max 3 concurrent contests. Confirm every terminal path (settle,
  cancel, expire, dispute-void) releases the slot. A leaked slot silently locks a user out.
- **Time windows.** Trailing-24h loss/entry/deposit caps read from the immutable ledger. Confirm
  every timestamp is UTC and the window boundary is computed consistently — a timezone-naive
  comparison here is a limit bypass.
- **Limit raise delay.** Raising a cap is delayed 24h, lowering is instant. Confirm the delay
  can't be bypassed by lowering and re-raising, or by a second pending raise.
- **Refund completeness.** On cancel/expire, is *everyone* who escrowed refunded, including in a
  partially-accepted room (Phase 3.4)? Is the rake genuinely zero on every refund path?
- **Dispute `resettle` / `void`.** Do these maintain the reconciliation invariants? Can a
  resettle double-pay a player who was already paid? Is there an admin audit row for each?

**CS2 pipeline**

- **Share-code codec.** Encoding exists purely so the codec can be round-trip tested — confirm
  the round-trip test actually exists and covers edge values (all-zero, all-max, boundary of the
  144-bit space). A decoder that drifts doesn't fail loudly; it grades the wrong match.
- **Chain cursor.** Confirm each documented status behaves as specified: 200 advance, 202 normal,
  412 stop-and-reprompt, 403 chain-broken, 429/5xx back-off-cursor-untouched. **Getting permanent
  failures wrong is a shared-fate problem** — Valve temporarily blocks an API key that keeps
  presenting bad auth codes, which takes out every user, not one.
- **`MAX_CODES_PER_SYNC`.** What happens to a user who's been away long enough to exceed it? Do
  they catch up over successive cycles, or silently fall behind forever?
- **Ordering.** Sync runs before pools settle. Confirm that ordering is guaranteed rather than
  incidental, and that a slow sync can't let a pool settle against a stale chain.
- **Roster verification.** Confirm the SteamID64-in-roster check can't be satisfied by a
  spectator, coach, or a re-used ID.

**Security and general production readiness**

- Authorisation on every admin route; confirm `admin_audit` rows are written on **every** admin
  write, not most of them.
- SSE `/events/stream` ticket handshake: can a ticket be replayed, or used for another user's
  stream?
- Idempotency keys on every money-moving endpoint.
- Input validation on anything user-supplied that reaches a query.
- PII and retention in `raw_payloads` — what's stored, for how long, and is any of it personal
  data you'd have to delete on request?
- Structured logging with a correlation ID through enqueue → form → grade → settle. Without it,
  debugging a live settlement failure is guesswork.
- N+1 queries and missing indexes on the settlement worker's hot path; it will be your first
  scaling problem.
- Migration reversibility: does every migration have a tested downgrade? Does any migration lock a
  table long enough to matter at production size?
- Secrets: confirm no keys in the repo, and that the GC sidecar's shared secret and the Steam API
  key aren't logged anywhere.

---

## Phase 7 — Write the plain-English explainer

**This is a required deliverable, not a nice-to-have.** Write `WHAT_CHANGED.md` for a reader who
is smart but is *not* a statistician and may not have written the code. Assume they will read it
to decide whether to trust the system, and possibly to explain it to someone else.

Rules for this document:

- **Plain language first, precision second.** Where you need a technical term, define it in the
  same sentence you first use it.
- **No unexplained jargon.** "Student-t predictive," "beta-binomial," "overdispersion," "ECE" —
  each gets one plain sentence. Example of the register to aim for: *"We were pretending we knew
  exactly how streaky each player is. We only had about 27 games to judge that from, which isn't
  enough to be sure. The new maths admits that uncertainty, which makes the quoted percentage
  honest."*
- **Lead with what it means for a player**, then how it works, then what changed in the code.
- **Be honest about what's still broken.** A section titled "What we still don't know" is more
  trustworthy than a clean bill of health, and this system has real open items.

Required structure:

1. **The one-paragraph summary** — what this pass was for and whether the system is now safe to
   put in front of real users.
2. **How Money Match decides your bar** — the whole pipeline in plain English, no formulas:
   we look at your recent games → we work out your typical result and how much you vary → we set
   a target you'd hit about 35/20/10% of the time → everyone in the room pays in → whoever hits
   their target splits the pot minus our cut.
3. **What was broken, and what it meant for a real player.** One subsection per fix. Each gets:
   *what was wrong* (one sentence), *what a player would have experienced* (one sentence), *what
   we changed*, *how we know it's fixed* (name the test). Use the research's numbers — "a bar we
   advertised as 10% was actually cleared 23% of the time by anyone playing Premier" is
   understandable by anyone; "mode pooling induces a mixture-distribution bias" is not.
4. **What we found ourselves** — the Phase 6 audit findings, same format.
5. **How the system works now, end to end** — a walkthrough of one contest from join to payout,
   naming the safety checks it passes through and what each one is for.
6. **How to tell if it's working** — the dashboards and alerts, what a healthy number looks like,
   and what to do when it isn't. Point at `RUNBOOK.md` for the procedures.
7. **What we still don't know** — open questions, unverified assumptions, deferred items, and
   anything needing legal or product input rather than engineering. Pull from
   `OPEN_QUESTIONS.md`.
8. **What has to happen before real money** — the remaining gate list, with owners where you can
   infer them.

Include a short glossary at the end: bar, clear rate, rake, escrow, pot, EWMA, prior, shrinkage,
calibration, share code, Game Coordinator, sidecar, room, bucket, fill rate.

---

## Definition of done

- [ ] Full test suite green, with **more** tests than the baseline recorded in Phase 0.1
- [ ] `alembic check` clean; every new migration has a tested upgrade **and** downgrade
- [ ] Golden snapshot file updated, with every diff explained in a commit message
- [ ] Money invariants hold under property-based testing
- [ ] Geo-fence fails closed and is proven by test
- [ ] Bar mathematics is versioned; in-flight contests settle under the math they were quoted
- [ ] Calibration harness exists and produces a curve from backtest data
- [ ] Fill rate, time-to-fill and settlement success are measurable with bots excluded
- [ ] `AUDIT_FINDINGS.md`, `OPEN_QUESTIONS.md`, `RUNBOOK.md`, `WHAT_CHANGED.md` all written
- [ ] No production system was touched

---

## How to work through this

Go in phase order. Phases 1 and 2 are the load-bearing ones; if you run short of time, a
completely finished Phase 0–2 plus Phase 6 plus Phase 7 is far more valuable than a half-finished
sweep of everything.

Report progress as you go with a short status after each phase: what you changed, what you found,
what surprised you, and whether anything in this brief turned out to be wrong when checked against
the actual code. **The research document was written without reading the source.** If the code
disagrees with it, the code wins — say so clearly, and put it in `OPEN_QUESTIONS.md` rather than
quietly working around it.
