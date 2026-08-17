# Money Match — Deep Research: Games, Matchmaking, Bar-Setting, and Launch Readiness

**Prepared 17 August 2026.** Companion to `IMPLEMENTATION_STATUS.md` (commit `ede7ce6`).

Every number in this document is either cited to a source or reproduced by the simulation
script delivered alongside it (`analysis.py`). Where I disagree with the advisor memo you
received, I say so explicitly and show the arithmetic.

> **Not legal advice.** I am not a lawyer. §5 summarises publicly reported regulatory activity
> and publisher contract language so you can brief counsel efficiently. It is not a substitute
> for the state-by-state opinion you need before real money moves.

---

## 0. The five findings that changed my view

1. **The binding constraint on adding games is publisher contract law, not API availability.**
   Riot ("Your product cannot feature betting or gambling functionality") and Supercell
   ("betting on the outcome of matches in which you participate as a player, irrespective of
   whether or not there is a fee or stake involved") both prohibit exactly what you do. That
   removes League, Valorant, TFT, 2XKO, Clash Royale, Brawl Stars and Clash of Clans in one
   line each — before any engineering conversation. And **PUBG, which you already ship**, has a
   developer-terms clause you are plausibly breaching today.

2. **Your worst statistical defect is not the Gaussian assumption. It is mode pooling and a
   headshot-percentage exploit — and both are live correctness bugs, not modelling niceties.**
   Pooling Wingman and Premier into one `cs2_kills` model makes a bar quoted at 10% clear at
   **23.2%** for a player who queues Premier — a **2.35×** mispricing they choose freely. And a
   player who deliberately takes 4 kills with headshot-only weapons clears a 60% headshot bar
   priced at 5% about **51%** of the time — a **10×** mispricing that requires no tooling and no
   collusion, just a Deagle.

3. **The plug-in normal is biased, and the fix is three lines.** You place bars at
   `μ̂ + k·σ̂` using point estimates from ~27 effective samples. Ignoring that σ̂ is itself
   estimated inflates every hard bar's true clear rate from 10% to **11.1%** (a 16% relative
   error, straight out of your pot math). Swapping the plug-in normal for a Student-t
   predictive with `ν = n_eff − 1` restores the mean to **9.9%** exactly. That is a strictly
   better answer to "what's defensible here?" than the lognormal branch you already built.

4. **Sandbagging is far faster than your docs assume.** The advisor said "roughly ten bad
   matches." It takes **three**. Three deliberately-tanked matches under an EWMA half-life of
   10 move a hard bar from 21 kills to 20 and lift the true clear rate from 10% to **29.3%** —
   a 2.9× edge for twenty minutes of work. One bar increment is worth **3.2–7.4 percentage
   points** of clear probability; your bars are quantised far more coarsely than your risk
   tolerance.

5. **Collapsing buckets is worth more than every other liquidity idea combined, and it is a
   config change.** At 200 joins/day, 108 buckets fills **23.7%** of tickets inside the TTL with
   a 51.8-hour expected wait. Twelve buckets fills **99.8%** at 5.8 hours. Four buckets fills
   100% at 1.9 hours. There is no growth-marketing plan that beats a factor of four in the
   denominator.

**On the advisor's two rankings:** I agree hard on "do not add games" and "do not add
house-guaranteed pots," and §1 and §5 give you sharper reasons than the memo did. I partially
disagree on round-normalisation being "the highest-leverage change" — §2.4 shows it is worth
about 10% of relative spread in the *independent* case and can be **counterproductive** in the
realistic CS2 case, because round count and kills-per-round are negatively correlated. It is
still worth doing, but for a different reason: cross-mode comparability, not variance
reduction.

---

## 1. Which games to add

### 1.1 The screen that actually matters

Most people evaluate a title on "does it have an API." That is the third question. The order is:

| # | Question | Why it kills a title |
| --- | --- | --- |
| 1 | Does the publisher's ToS or developer policy prohibit wagering on matches? | Contract breach; instant shutdown; an investor's diligence lawyer finds it in ten minutes |
| 2 | Can a player **cherry-pick** which match counts? | Destroys the integrity story that is your entire moat |
| 3 | Is there a per-match, per-player stat feed tied to a verifiable identity? | No feed, no grading |
| 4 | Is the metric robust to deliberate degenerate play? | §2.2 — this is the one nobody checks |
| 5 | Is the API official, or a scrape/bot? | Third-party APIs are a single point of failure you don't control |

### 1.2 The screen applied

| Title | Publisher stance on wagering | Match feed | Anti-cherry-pick | Verdict |
| --- | --- | --- | --- | --- |
| **League of Legends / Valorant / TFT / 2XKO / LoR** | ❌ **"Your product cannot feature betting or gambling functionality."** Riot Developer Policies | Excellent official API | Yes | **Excluded. Not negotiable.** |
| **Clash Royale / Brawl Stars / Clash of Clans** | ❌ Supercell ToS bans "betting on the outcome of matches in which you participate as a player, irrespective of whether or not there is a fee or stake involved" | Excellent official API | Yes | **Excluded.** Note this language explicitly forecloses the "but it's peer-to-peer skill" argument |
| **PUBG** *(you already ship this)* | ⚠️ Dev ToS: "You may not charge money for exclusive access to features that are based, in whole or in part, on data gained from the PUBG API" | Official, throttled 9/min | Yes | **Existing exposure — see §1.4** |
| **Rocket League** | Silent | ❌ Stats API is a **local WebSocket for live overlays**, opt-in per client via `TAStatsAPI.ini`. No match history, no server-side history | ❌ | **Excluded — no verifiable feed** |
| **Apex Legends** | Silent | ❌ No official API; only `apexlegendsapi.com` scrapers | ❌ | **Excluded** |
| **Marvel Rivals** | Silent (NetEase) | ⚠️ Only third-party `marvelrivalsapi.com` | ⚠️ | **Excluded for now** — third-party dependency is strictly worse than your GC sidecar, because you don't even control the failure |
| **Chess (Lichess)** *(shipped)* | ✅ ToS silent on gambling; explicitly permits commercial use: "You can use our services for your own personal or commercial use" | Excellent, open | Yes | **Your safest title, legally** |
| **Chess.com** | ✅ Public Published-Data API, no auth, IP restrictions only, "contact legal@chess.com" for commercial | Monthly game archives, full PGN | Yes | **Best single expansion — see §1.3** |
| **Dota 2 (OpenDota)** *(shipped)* | ✅ Valve silent on wagering in Web API ToU | Official + OpenDota | Yes | Fine |
| **CS2** *(shipped)* | ⚠️ Web API ToU silent on wagering, **but SSA prohibits Automation** — see §1.4 | GC + share-code chain | **Yes — best in class** | Your moat |
| **osu!** | Silent; official API v2 with OAuth 2 | Official, per-play scores | Partial (recent-scores endpoint) | **Interesting — see §1.3** |

### 1.3 If you add exactly one thing, add these — in this order

**(a) CS2 Premier as a separate market from CS2 Competitive and CS2 Wingman. Zero new adapters.**

This is not "adding a game," it's fixing §2.3's correctness bug. But it also gives you three
markets where you had one, and each has a tighter, more honest distribution. Do this first
because it is a bug fix that happens to look like a feature.

**(b) Chess.com.** Chess is already shipped, the engines are game-agnostic, the API is public
and unauthenticated, and Chess.com's active user base is roughly an order of magnitude larger
than Lichess's. You are not adding a *vertical*, you are adding **liquidity to a vertical you
already run** — which is the only kind of expansion that helps you at launch. The `chess_moves`
prior is the single most rigorously fitted piece of modelling in your codebase (4,647 games,
`mean_moves(elo) = 16.65 + 0.01013·elo`) and it transfers directly, because Chess.com Elo and
Lichess Elo are both Glicko-ish ratings on comparable populations after an offset. Fit the
offset from a few hundred dual-account players and you're done.

Cost estimate: one adapter, one prior offset, no new legal analysis. This is a week.

**(c) osu! — but only if you want a strategically different metric.**

osu! is the only candidate on the list where **your performance does not depend on nine other
people.** Score, accuracy and pp are functions of you and a fixed beatmap. That eliminates the
`μ_player + team + opponents + map + mode + noise` decomposition problem entirely — the
variance really is yours. Statistically it is the cleanest market you could possibly run, and
the calibration curve you'd get would be tight enough to put on a slide.

Two caveats: the osu! API v2 exposes *recent scores* rather than a linked-list chain, so
cherry-picking is a live risk you'd have to design around (mitigate by scoping the wager to a
specific beatmap + mods and taking the first submitted play in the window). And the audience
overlap with a CS2/Dota wagering product is thin.

**Everything else: no.** Not because the engineering is hard, but because §3 shows that every
new game divides an already-empty market.

### 1.4 The exposure on games you already ship

Two things I'd want an answer prepared for, because a technical diligence process will find
both:

**Steam Subscriber Agreement, §4 (Automation).** The SSA states: *"You may not use any form of
scripts, bots, macros, or other non-human-controlled systems ('Automation') to interact with
Content and Services on Steam in any manner."* Your GC sidecar is precisely that. Separately
the SSA prohibits using an account "to enable a violation of this Agreement by others, such as
through their commercial use of Steam Content and Services." Your own docs already flag this;
what they don't flag is that the **Steam Web API Terms of Use also cap you at 100,000 calls per
day**, which is a hard scaling ceiling on chain-walking — roughly 69 chain syncs per minute
across your entire user base, before you've resolved a single share code.

*The honest posture:* this is a de-facto-tolerated practice. Leetify, csgostats.gg and Scope.gg
have all run GC bot fleets for years. The risk is real but empirically survivable, and the
mitigation is architectural, not legal:

- **Run a fleet, not a process.** N ≥ 3 Steam accounts behind a rotating pool with health
  checks; a ban takes out 1/N of capacity, not 100%.
- **Give those accounts no other surface.** No inventory, no trading, no friends, no game
  purchases beyond CS2, no community activity. The accounts that get actioned are the ones
  doing trading and inventory automation.
- **Fail loud.** Today `gc_client.health()` returns the same shape whether the sidecar is
  up-but-unattached or unreachable, and the router discards the `detail` field that would
  distinguish them. That is the bug behind your three days of `ready:false`. Fix the shape,
  then page on it.
- **Have the fallback written down.** If Valve breaks the GC interface, what settles CS2? The
  answer today is "nothing." A written answer — even "we fall back to FACEIT's official API for
  FACEIT matches and refund everything else" — is worth having in the room.

**PUBG developer terms.** *"You may not charge money for exclusive access to features that are
based, in whole or in part, on data gained from the PUBG API."* Your read is presumably that an
entry fee into a peer-funded pot is not a charge for *access to a feature*. Krafton's read might
differ. Given §3 says PUBG is diluting your liquidity anyway, the cheap move is to **shelve PUBG
at launch** — you get the liquidity benefit and the ToS exposure disappears in the same commit.

---

## 2. Bar-setting: what's actually wrong, ranked by damage

All figures below are reproducible with the delivered `analysis.py`.

### 2.1 The ranking

| # | Defect | Magnitude | Type | Cost to fix |
| --- | --- | --- | --- | --- |
| 1 | Wingman/Premier/Competitive share one model | **2.35×** mispricing at hard | Correctness bug | Hours |
| 2 | Headshot % is gameable by playing for few kills | **~10×** mispricing | Exploit | Days |
| 3 | Kills graded `≥` vs `>` on a discrete count | **27%** relative | Correctness bug | Minutes |
| 4 | Plug-in normal ignores parameter uncertainty | **16%** relative bias at hard | Modelling | Hours |
| 5 | Negative-binomial overdispersion in kills | **22%** relative at hard | Modelling | Days |
| 6 | Per-player calibration dispersion (±4.8pp at hard) | Irreducible-ish | Modelling | Weeks |
| 7 | Bar increment coarseness (K/D at 0.05) | **±3.7pp** at easy | Config | Minutes |
| 8 | Round normalisation | **−10% to +11%** spread | Modelling | Days |

Note that #1, #2, #3 and #7 are all cheaper to fix than #8, and all four are larger. The memo
you received ranked round-normalisation first; the arithmetic doesn't support that.

### 2.2 The headshot-percentage exploit — fix this before you take a dollar

Headshot % is `headshots ÷ kills`. Its sampling variance is `p(1−p)/K`, so it **explodes as the
kill count falls** — and the kill count is under the player's control.

Simulated with true headshot rate 42% and a realistic negative-binomial kill count, a player
whose model reads μ=43.5, σ=13.2 gets a hard bar of 60%:

| Behaviour | P(clear a 60% bar) |
| --- | --- |
| Normal 17-kill Premier game, 42% aim | **5.0%** |
| 4 kills, 42% aim (die early, don't force it) | **20.3%** |
| 4 kills, Deagle/AWP-only play (62% headshot rate) | **51.0%** |
| 2 kills, Deagle-only | **38.4%** |

A bar you quote at 10% clears **51%** of the time for a player who buys a Deagle, takes two
peeks, and doesn't care about the round. This costs them nothing — they still get their entry
back if they miss, and they don't even have to try to win the match. It is discoverable by
accident, and once one person posts it to Reddit your headshot market is finished.

**The three fixes, in order of preference:**

1. **Add a kill floor to the market definition.** A headshot % wager only grades against matches
   with ≥ 12 kills. Simple, explainable on the card ("counts on games where you get 12+ kills"),
   and it collapses the exploit because the variance term shrinks by 3×. This is the same class
   of rule as your existing round floor and it fits your architecture in an afternoon.
2. **Grade on headshots-per-round instead of headshots-per-kill.** Turns a ratio-of-counts with
   a controllable denominator into a count with a fixed, observable denominator. Strictly better
   statistically. Requires a new market and a new prior.
3. **Model it properly as beta-binomial and place the bar on the predictive distribution of
   `H/K` marginalised over the kill count.** Correct, but it *prices* the exploit rather than
   removing it — a low-kill player still faces a much easier bar, they just get told so. Do this
   in addition to (1), not instead of it.

Do (1) this week regardless of what else you do.

### 2.3 Mode pooling is a live correctness bug

Your `IMPLEMENTATION_STATUS.md` marks this 🟡 "unverified." Verify it today. Simulating a
50/50 mix of Premier (μ=17, σ=5.5) and Wingman (μ=9.5, σ=3.8) into one `cs2_kills` model:

| Difficulty | Pooled bar | Quoted | Actual, if they queue Premier | Actual, if Wingman | Mispricing |
| --- | --- | --- | --- | --- | --- |
| Easy | 16 kills | 32.3% | **57.1%** | 4.3% | 1.77× |
| Medium | 18 kills | 21.5% | **42.6%** | 1.3% | 1.99× |
| Hard | 21 kills | 9.9% | **23.2%** | 0.1% | 2.35× |

The aggregate is roughly fine — which is exactly why it's dangerous, because a naive
calibration harness that pools across modes would show it as calibrated. The damage is
**conditional and self-selected**: the player chooses the mode after the bar is set. Any player
who notices this and queues Premier-only faces a 23.2% clear rate on a bar sold at 10%. Against
a peer-funded pot of three casuals, that is a very large positive-EV position.

**Fix:** `metric_models` is keyed `user × game × metric`. Make it `user × game × mode × metric`,
or equivalently register `cs2_premier_kills`, `cs2_competitive_kills`, `cs2_wingman_kills` as
distinct markets. The GC scoreboard reply already carries enough to classify the mode, and your
round floors (16 Premier/Competitive, 9 Wingman) prove you have the discriminator. Then make
the wager *bind* to the mode: a Premier wager grades only against Premier matches, and a
Wingman match in the chain is skipped, not graded.

Side benefit: this converts one mushy market into three tight ones, which is the only kind of
market multiplication that doesn't hurt liquidity, because you can gate the queue to the modes
that actually have traffic.

### 2.4 On round normalisation — I disagree with the memo

The claim was that round count "lands entirely in σ" and normalising is the highest-leverage
change available. Decomposing the variance of a player's per-match kills:

```
Var(kills) = E[R]·Var(per-round kills)  +  E[R]²·Var(form)  +  Var(R)·E[kpr]²
           =        14.1  (47.9%)       +      9.7 (33.0%)  +     5.6 (19.1%)
```

Round count is **19%** of kills variance, not most of it. The dominant term is within-match
sampling noise, which normalising by rounds does not remove — it is the irreducible randomness
of one match. Normalising cuts the relative spread from 37.6% to 33.8%, i.e. about **10%
tighter bars**.

Worse, that 10% assumes rounds and kills-per-round are independent. In CS2 they are
**negatively correlated**: a 13-3 stomp is *short* and *high* kills-per-round; a 13-11 grind is
*long* and *low* kills-per-round. The two partially cancel in the total, so total kills is more
stable than either component:

| corr(rounds, kpr) | rel-sd of kills | rel-sd of kills/round | change |
| --- | --- | --- | --- |
| 0.0 | 37.8% | 34.3% | **−9.2%** |
| −0.3 | 35.3% | 34.4% | −2.4% |
| −0.5 | 33.4% | 34.6% | **+3.6%** |
| −0.7 | 31.3% | 34.6% | **+10.6%** |

At realistic correlations, quoting kills-per-round makes your bars *wider*, not narrower.

**So why do it anyway?** Two reasons that survive:

- **Cross-mode comparability.** Once you split Premier/Wingman (§2.3), a per-round metric lets
  a single prior serve both modes and lets a player's Wingman history inform their Premier
  model. That is a genuine hierarchical-modelling win.
- **Fairness optics.** "You got 19 kills but the game was 13-3, so only 16 rounds" is a real
  complaint you will receive in your dispute queue, and per-round grading answers it.

Measure the correlation on your own data before committing. It is a two-line query once you
have collected a single match — which, per §6, you haven't.

### 2.5 Kills: the discreteness fix is free and larger than the distribution fix

Kills is an integer. Your bar is an integer. Your clear probability is computed from a
continuous normal. Three different answers, μ=17, σ=6:

| Difficulty | Bar | Quoted (normal) | Negative binomial, `P(X ≥ bar)` | Negative binomial, `P(X > bar)` |
| --- | --- | --- | --- | --- |
| Easy | 19 | 36.9% | 36.9% | 31.2% |
| Medium | 22 | 20.2% | 21.4% | 17.4% |
| Hard | 25 | 9.1% | **11.1%** | 8.8% |

Two separate errors here, and the second is bigger than the first:

1. **Distribution.** Negative binomial (overdispersion index 2.12) gives 11.1% where the normal
   says 9.1% — a **22% relative** error on the hard tier. Real, but it takes a fitting exercise
   to fix.
2. **Semantics.** `P(X ≥ 25) = 11.1%` versus `P(X > 25) = 8.8%` is a **27% relative** gap that
   depends entirely on whether your grading code writes `>=` or `>`. Go read that line. Whatever
   it says, make the clear-probability calculation match it exactly, and put the convention on
   the card ("**25 or more** kills"). This costs you five minutes and is worth more than the
   distributional fix.

The same applies to `chess_moves` (integer) and to any bounded-increment metric.

### 2.6 The error nobody is looking at: you don't know σ either

This is the finding I'd put on the technical slide, because it reframes the whole problem.

Your EWMA with half-life 10 over a 50-match bootstrap has an **effective sample size of 27.1**
(`n_eff = (Σw)²/Σw²`). Not 50 — 27. From 27 samples, σ̂ has a relative standard error of about
14%, and that error propagates straight into bar placement. Monte-Carlo over 4,000 simulated
players whose true process is exactly N(17, 5.5):

| Difficulty | Quoted | **Mean realised** | SD across players | 10th–90th percentile |
| --- | --- | --- | --- | --- |
| Easy | 35.0% | 35.8% | 7.6pp | 29.3% – 42.8% |
| Medium | 20.0% | 21.3% | 6.5pp | 13.8% – 29.3% |
| Hard | 10.0% | **11.6%** | 4.9pp | **5.1% – 18.2%** |

Read the last row carefully. Even with the Gaussian assumption *perfectly correct*, one in ten
of your hard-tier players is being sold a bar they clear 18% of the time, and one in ten a bar
they clear 5% of the time. The pot is peer-funded, so those two players are in the same room
taking money off each other, and the 18% player has a ~3.6× edge over the 5% player before
either of them does anything clever.

**Fix #1 (three lines, removes the bias exactly).** Use the Student-t predictive rather than
the plug-in normal:

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

The `sqrt(1 + 1/n_eff)` term is the predictive-variance inflation for a *new* observation; the
`t` quantile handles the σ uncertainty. Together they are the textbook correction and they are
exactly right. Notably this **also subsumes your `effective_sigma` floor's motivation** in a
principled way — the floor was papering over the fact that a small-n player's spread estimate
is untrustworthy, and the t-predictive says so properly. Keep the floor as a guard rail, but
it should stop binding for most players.

**Fix #2 (what shrinkage actually buys — less than you'd hope).** I tested hierarchical
shrinkage of σ̂ toward a population σ over a population with true σ ~ Gamma(mean 5.5, sd 1.2):

| Method | Mean realised | SD | **MAE vs 10% target** |
| --- | --- | --- | --- |
| Plug-in normal (today) | 11.10% | 4.83pp | 3.80pp |
| Student-t predictive | 9.89% | 4.50pp | 3.58pp |
| t-predictive + shrink w=10 | 9.39% | 4.23pp | **3.45pp** |
| t-predictive + shrink w=25 | 9.25% | 4.30pp | 3.52pp |
| t-predictive + shrink w=60 | 9.24% | 4.79pp | 3.94pp |

Shrinkage buys ~4% of MAE and starts hurting past w≈25. The dispersion is dominated by
estimation noise, not by population heterogeneity — so **the fix is more data, not a better
prior.** Which leads to:

**Fix #3 (decouple the half-lives).** Form drifts; volatility doesn't. There is no reason to
estimate μ and σ on the same window. Simulating a drifting-μ, fixed-σ process:

| half-life μ | half-life σ | window | Mean realised | MAE |
| --- | --- | --- | --- | --- |
| 10 | 10 | 50 | 9.98% | 4.32pp |
| 10 | 20 | 50 | 10.07% | 4.07pp |
| 10 | 30 | 50 | 10.20% | 4.05pp |
| **10** | **30** | **100** | 9.90% | **3.80pp** |
| 10 | 50 | 150 | 9.82% | 3.80pp |

`hl_μ = 10, hl_σ = 30, window = 100` buys a 12% MAE reduction for a config change and a bigger
bootstrap fetch. Diminishing past that.

**Fix #4 (the one that actually closes the gap): pool σ across metrics.** A player's *relative*
volatility is largely a property of the player, not the metric — someone who is streaky on
kills is streaky on K/D. A multivariate model that estimates one player-level volatility factor
from all three CS2 metrics simultaneously roughly triples your effective sample size for σ.
This is the genuinely defensible piece of IP in the whole stack and it is the thing I would
build if you want an answer to "what's proprietary here?"

### 2.7 Bar quantisation — your increments are too coarse

One increment of bar movement is worth this much clear probability:

| Metric | Increment | At easy | At hard | Rounding error alone |
| --- | --- | --- | --- | --- |
| `cs2_kd_ratio` | 0.05 | **7.41pp** | 3.51pp | **±3.70pp** |
| `cs2_kills` | 1.0 | 6.74pp | 3.19pp | ±3.37pp |
| `cs2_headshot_pct` | 1.0 | 3.09pp | 1.46pp | ±1.54pp |
| `cs2_kills_per_round` | 0.01 | 1.48pp | 0.70pp | ±0.74pp |

A K/D bar quoted at "35%" is, from rounding alone, somewhere between 31.3% and 38.7%. That is a
larger error than the negative-binomial correction you'd spend a week on. **Change
`METRIC_BAR_INCREMENT['cs2_kd_ratio']` from 0.05 to 0.01.** K/D is already displayed to two
decimals everywhere in CS2; nobody will notice except your calibration curve.

(And delete `cs2_adr` from that dict — it's a market you retired in migration 0024.)

### 2.8 A better prior, using data you already fetch

Two concrete improvements to `cs2_prior`:

**Use the fields Steam already returns.** `_derived(kd)` scales generic headshot%/kills defaults
by K/D, ignoring `total_kills_headshot` and `total_matches_played` in the same response. For
your test account (K/D 0.606, actual HS% 36.6, actual 8.19 kills/match) it seeds HS% 42.3 and
kills 10.9 — quoting easy bars of 47% and 13 kills against a player whose real form is 36.6%
and 8.19. That player will essentially never clear, will lose four contests, and will churn.
Direct computation from the returned totals is a five-line change and it is the single
highest-ROI bug on your list after the sidecar.

**Condition on CS Rating, not lifetime K/D.** Your own docs call lifetime K/D a weak signal —
it's cumulative across casual, deathmatch and bot games. Premier CS Rating is the right
covariate and it's well-distributed: per Leetify data aggregated for Season 4 (March 2026),
21.2% of players sit below 5,000, 23.9% at 5,000–9,999, 26.5% at 10,000–14,999, 19.9% at
15,000–19,999, 5.5% at 20,000–24,999, 2.4% at 25,000–29,999 and 0.6% above 30,000. Roughly half
the player base is between 5,000 and 15,000.

That's enough spread to fit `μ_metric = a + b·rating` exactly the way you fitted
`mean_moves(elo) = 16.65 + 0.01013·elo` for chess — which is, again, the most credible
modelling in your codebase. Do the same thing for CS2 and you have a second empirically-fitted
prior instead of an empty `_PRIORS` dict. You need ~500 rated players' match histories, which
you can gather from public data without a single wager being placed.

**Note also that `host_rating()` returns `None` for CS2 regardless**, because it reads
`formats`/`primary_speed` from a chess-shaped profile snapshot. Fix that at the same time or
the prior can't be conditioned on anything.

### 2.9 What TrueSkill 2 already solved for you

Microsoft's TrueSkill 2 paper is the closest published prior art to what you're building, and
it independently validates two of the memo's points and contradicts a third. Worth reading in
full; the relevant results:

- **Kill counts are modelled with an explicit time-played scaling:**
  `count ~ max(0, N((w_p·perf + w_o·perf_opp)·timePlayed, v·timePlayed))`. Their reason for the
  scaling is the same as the round-normalisation argument — and note that they scale both the
  mean *and* the variance by match length, which is the piece §2.4's naive normalisation gets
  wrong.
- **Squad size has a measurable, separate effect.** TrueSkill 1 assumed squad skill was the sum
  of individual ratings; the data showed larger squads systematically outperform that. They
  added an explicit `squadOffset(squad size)` term. This is direct empirical support for the
  party-stacking concern — **stacking is a real, measurable performance boost, not a theory.**
  Your detection signal (repeated co-occurrence of the same SteamIDs across a player's chain) is
  the right one, and the response should be a party-size term in the model rather than a ban.
- **Modes share a base skill with per-mode offsets:** `skill_mode = w_mode·base + offset_mode`.
  This is precisely the hierarchical structure §2.3 needs — it lets you split Premier/Wingman
  *without* fragmenting each player's history, because a new mode inherits from the base.
- Headline: 68% predictive accuracy vs TrueSkill 1's 52% on Halo 5.

You should be able to say in a pitch: "we're doing per-player threshold pricing on the
TrueSkill 2 generative structure, calibrated against realised outcomes." That is a real
sentence with real content behind it.

---

## 3. Liquidity — the number that decides whether you have a company

### 3.1 The arithmetic

A pool needs 3–4 entrants in the same `game × metric × difficulty × entry` bucket. Modelling
arrivals as Poisson within a bucket, with a composition-acceptance rate `q = 0.5` (the fraction
of candidates surviving your band + spread cap) and a 24-hour TTL, the probability a tagged
ticket finds two compatible partners:

| Daily joins | **B=108** (today) | **B=36** (CS2 only) | **B=12** (+ collapse entry) | **B=4** (+ collapse difficulty) |
| --- | --- | --- | --- | --- |
| 50 | 2.3% / 207h | 15.4% / 69h | 61.6% / 23h | **98.6% / 7.7h** |
| 200 | 23.7% / 52h | 76.5% / 17h | **99.8% / 5.8h** | 100% / 1.9h |
| 1,000 | 94.5% / 10.4h | 100% / 3.5h | 100% / 1.2h | 100% / 0.4h |
| 5,000 | 100% / 2.1h | 100% / 0.7h | 100% / 0.2h | 100% / 0.1h |
| 20,000 | 100% / 0.5h | 100% / 0.2h | 100% / 0.1h | 100% / 0.03h |

(Cells are *fill rate inside TTL* / *expected time to fill*.)

Read across the 200-joins row: you go from a **23.7% fill rate with a two-day wait** to a
**99.8% fill rate with a six-hour wait** purely by changing how you index the queue. Nothing
else on your roadmap has that magnitude.

Read down the B=108 column: you need roughly **1,000 joins per day** — call it 3,000–5,000
weekly actives — before the current bucketing works at all. That is not a launch number.

### 3.2 The four collapses, in order

**1. CS2 only at launch.** Kills B from 108 to 27 immediately, concentrates every user in the
vertical where your verification is deepest, and removes the PUBG ToS exposure (§1.4) as a side
effect. Chess can stay as a soft-launch second vertical because it costs you nothing to run and
its liquidity is independent (chess players aren't the marginal CS2 entrant).

**2. Collapse the entry dimension with pro-rated payouts.** Match on `metric × difficulty` and
let entry float. A player entering $10 into a pot with $10/$25/$50 entrants takes a
proportional share: `payout_i = distributable × (entry_i / Σ entry) ` among clearers, or more
precisely `payout_i = distributable × entry_i / Σ_{clearers} entry_j`. Your `Split` invariant
(`sum(payouts) + rake == pot`) handles this unchanged — the remainder still lands in rake.
Cuts B by 3×.

**3. Collapse the difficulty dimension by making difficulty a *personal* attribute, not a room
attribute.** This is the non-obvious one and it's the biggest single win available. Right now
easy/medium/hard is a bucket key. But a pool where everyone has a personal bar at their own
target clear rate does not require everyone to have chosen the *same* target — it only requires
the payout to reflect the difference. Give a hard-tier entrant a larger share weight than an
easy-tier entrant in the same pot:

```
weight_i   = 1 / p_target_i          # easy 2.86, medium 5.0, hard 10.0
payout_i   = distributable × weight_i·entry_i / Σ_{clearers} weight_j·entry_j
```

Expected weighted claim is equalised across tiers by construction, so this is fair, it
preserves the peer-funded structure exactly, and it cuts B by another 3×. It also removes your
`composition_ok` band problem for difficulty, because tiers no longer need to agree.

**Caveat worth thinking through:** mixing tiers in one pot weakens the anti-shark property of
the shared room bar. Your §5.6 band rule (`p_i ∈ [p_target/2, min(2·p_target, 0.5)]`) exists to
stop a strong player dragging the bar. With personal bars and weighted payouts there is no
shared bar to drag — which is cleaner in one way and removes a safeguard in another. Model this
before shipping it.

**4. Widen the window and let pools fill asynchronously.** You already have `FOR UPDATE SKIP
LOCKED` match-on-write, so a pool that fills over hours costs you nothing architecturally. Note
the tension with §4.1 — a longer fill window is exactly what makes the free option valuable —
which is why the recommendation there is to separate *fill window* from *play window*.

**5. Only then, and probably never: house-guaranteed pots.** Agree completely with the memo.
Guaranteeing a pot converts you from a rake-taking intermediary into a **counterparty**, which
is the precise structural distinction §5 shows regulators used to justify cease-and-desists
against pick'em DFS operators. It is not a product experiment; it is a change to your legal
theory of the business. If you want a liquidity backstop that doesn't do that, the safe version
is **rake rebates** — cut the rake to zero on under-filled pools — which costs you revenue but
never puts platform money at risk on an outcome.

### 3.3 Batch versus greedy formation

Your engine is greedy (match-on-write, `SKIP LOCKED`). The academic result here is more
comforting than you'd expect: recent work on dynamic matching finds **neither batching nor
greedy dominates**, and both reach ~91% of optimal at a sojourn period of 6 and 95%+ at 18.
Greedy converges faster (O(1/τ) vs O(1/√τ)) and is preferable when sojourn times are short;
batching requires less information about arrival distributions but needs more patient
participants.

Practical read: **keep greedy.** Your fill problem is a *thickness* problem (§3.1), not a
*policy* problem, and no matching policy fixes an empty market. Revisit batching only if you
ever have enough traffic that room *quality* starts to bind before room *existence* does.

### 3.4 The bots are hiding the number you most need to know

`test_opponents.py` is well-built — real wallets, real ledger entries, no special case in the
money path, `is_enabled()` keyed off the user rather than the environment. But it means **your
fill rate is currently unmeasurable**, and fill rate is the metric that tells you whether you
have a marketplace.

Instrument it before launch: `fill_rate = rooms_formed / tickets_enqueued`, computed with bots
excluded, bucketed by `game × metric × difficulty × entry`, plus a `time_to_fill` histogram and
an `expired_unmatched` count. Ship a dashboard with one row per bucket. That single view will
tell you which collapses in §3.2 you actually need, and it is also the slide that answers "do
you have a marketplace or a demo?"

---

## 4. The economics of the free option and sandbagging

### 4.1 The free option is worth 1.4×–1.9×

Model: a player's match performance is `X ~ N(0,1)` after standardisation; the bar sits at
`z_k`. Before deciding whether to queue Premier, they observe a private signal
`S = ρX + √(1−ρ²)ε` — how their aim feels in deathmatch, whether they're tilted, whether their
stack is on. They play when `S > 0` (their better half of days) and otherwise let the 24-hour
window expire for a full refund.

| Difficulty | Base | ρ=0.3 | ρ=0.5 | ρ=0.7 |
| --- | --- | --- | --- | --- |
| Easy | 35% | 44.0% (1.26×) | 50.4% (1.44×) | 57.5% (1.64×) |
| Medium | 20% | 26.7% (1.34×) | 31.3% (1.56×) | 35.8% (1.79×) |
| Hard | 10% | 14.1% (1.41×) | 16.7% (1.67×) | 18.9% (**1.89×**) |

Note the option is **worth more at hard difficulty**, because tail probabilities are more
sensitive to a mean shift. Your highest-multiplier markets are your most exploitable ones.

Cashing that out in a four-handed $25 pool at 10% rake, where a "no one clears" outcome refunds
everyone:

| Scenario | EV per contest | ROI |
| --- | --- | --- |
| Everyone honest (all at 35%) | −$2.05 | −8.2% |
| Shark at ρ=0.5 (49.2%) vs three casuals | **+$4.47** | **+17.9%** |
| Shark at ρ=0.7 (57.3%) vs three casuals | **+$8.19** | **+32.8%** |
| Casual in a room with a shark | −$7.93 | **−31.7%** |

(Sanity check: four honest players sum to −$8.21 ≈ the $10 rake minus the no-clear refund mass.
Money conserves.)

A casual losing 31.7% per contest churns after four contests. That is the poker dynamic the memo
warned about, quantified.

### 4.2 What to actually do about it

Four options, and I'd do #1 and #4 together.

**1. Separate the fill window from the play window.** This is the key structural move. Today one
24-hour window does both jobs, which is why you have both a liquidity problem *and* a free-option
problem — and they pull in opposite directions.

```
Phase 1 (FILL):  ticket sits in queue for up to 24h. No escrow. Bar frozen at enqueue.
Phase 2 (LOCK):  room forms -> push notification -> 10-minute accept window -> escrow
Phase 3 (PLAY):  45-60 minutes to start a qualifying match. Expire -> refund.
```

Option value scales with how much private information you can gather before committing. Over 24
hours you can pick your day, warm up in deathmatch, and wait for your stack — plausibly ρ ≈
0.5–0.7. In a 45-minute window immediately after a push notification you get ρ ≈ 0.1–0.2, which
per the table above is worth 1.1× rather than 1.9×. **Same total wait for liquidity, ~80% of the
option value removed.** It also cuts your time-to-settlement from 24 hours to under an hour,
which is what makes the end-to-end demo video in §6 filmable.

**2. Calibrate on the *completing* population, not the modelled one.** This is the cheap,
self-correcting fix and I think it's underrated. If you set `k` so that the realised clear rate
*among players who actually play* is 35%, then whatever selection effect exists is priced into
the bar automatically. The pot math becomes correct, the multiplier becomes correct, and the
sharks' edge over casuals shrinks because everyone's bar has risen to reflect the average level
of selection. You never have to detect or prove selection is happening — you just have to
measure the outcome you care about. **This falls straight out of the calibration harness in §7
and it is the single best argument for building it.**

**3. Make no-show costly, carefully.** Retaining a fee on expiry is economically correct and
legally awkward — money moving on a contest that never happened is a worse fact pattern than
money moving on a contest that did. If you go here, prefer non-monetary friction: a cooldown
before re-queueing, a visible completion-rate badge, or exclusion from the leaderboard below
some completion threshold. Do **not** grade a no-show as a loss; "you cannot lose by not
playing" is a genuinely good consumer-protection property and it is worth more in a regulatory
conversation than the leakage costs you.

**4. Track completion rate as a first-class risk signal.** A player whose completion rate is
55% while the population sits at 85% is exercising the option, whether or not they're doing it
deliberately. That's a `risk_flags` row and a candidate for a bar adjustment. You already have
the detector infrastructure (`win_streak`, `pair_cap`); this is one more nightly pass.

### 4.3 Sandbagging is three matches, not ten

Simulating a player whose true process is N(17, 5.5), with a 50-match honest history, who then
plays deliberately bad matches (4 kills each):

| Tanked matches | μ̂ | σ̂ | Hard bar | **True clear rate** | Edge |
| --- | --- | --- | --- | --- | --- |
| 0 | 14.60 | 4.68 | 21 | 10.0% | 1.0× |
| **3** | 12.56 | 5.93 | 20 | **29.3%** | **2.9×** |
| 5 | 11.43 | 6.24 | 19 | 35.8% | 3.6× |
| 10 | 9.22 | 6.24 | 17 | 50.0% | 5.0× |
| 20 | 6.59 | 5.11 | 13 | 76.6% | 7.7× |

Three deathmatch-quality Premier games — about 90 minutes — buys a 2.9× edge. The reason it's so
fast is §2.7: one bar increment is worth 3.2 percentage points of clear probability at hard, so
you only need to move μ̂ by about one kill to move the bar by one step.

Note also that σ̂ *rises* while μ̂ falls (4.68 → 6.24), which partly offsets the bar drop — the
bar goes 21→20→19 instead of 21→19→17. That is an accidental safeguard, and it disappears if you
ever switch to a robust σ estimator. Be aware of the interaction.

**Countermeasures, in order:**

- **Asymmetric updating.** Bars rise fast and fall slow: `hl_up = 10, hl_down = 40`. This is the
  standard anti-sandbagging move and it's a five-line change to `compute_ewma`. Costs you a
  slower response to genuine decline, which is the right trade — a genuinely declining player
  clears less often and gets refunded, which is survivable; a sandbagger takes money from
  casuals, which isn't.
- **A floor on bar velocity.** No personal bar may fall more than X% per rolling 7 days,
  regardless of what the model says. Blunt, effective, trivially auditable.
- **Trimmed statistics.** Compute μ̂ over the middle 80% of the weighted sample. Kills off the
  cheapest version of the attack (a handful of near-zero games) at the cost of some responsiveness.
- **Your existing z-test detector, but on the right side.** Your sandbagging flag already
  z-tests recent form against the older baseline. Verify it triggers at *n=3*, not *n=10* — with
  σ=5.5 and three samples at 4 kills, `z = (4 − 17)/(5.5/√3) = −4.09`, which should fire
  comfortably. If it doesn't, your threshold is too loose.
- **Prior art exists and you should know about it.** US 9,349,249 B2, *"Anti-sandbagging in
  head-to-head gaming for enriched game play environment"* (Gamblit Gaming LLC, 2016) claims
  outlier-test-based detection (Grubbs', Dixon's Q), dynamic handicap adjustment, wager caps
  keyed to professed skill, automatic upward ranking adjustment when performance exceeds
  expectation, and escalating penalties. Read the claims before you build — partly to avoid
  reinventing it, partly because "we reviewed the prior art in this space" is a good answer to
  an investor's IP question. **Have counsel look at claim overlap** if you implement
  handicap-adjustment or bet-limiting keyed to detected sandbagging, which are the two closest.

### 4.4 Party stacking

TrueSkill 2's `squadOffset` result (§2.9) says this is real and measurable, not theoretical.
Your detection signal is right: repeated co-occurrence of the same SteamID64s in the roster
across a player's chain. The GC scoreboard reply gives you the full roster, so this is a query
over `cs2_matches`, not new plumbing.

Implementation sketch: for each settled match, compute `stack_size` = number of teammates who
appear in ≥ 40% of the player's last 20 matches. Then fit `μ_player + squadOffset(stack_size)`
and place the bar at the *expected* stack size for that player. A player who habitually
five-stacks gets a bar that reflects it; a solo-queue player who suddenly five-stacks is a risk
flag. This is a genuinely differentiated feature and it maps onto published prior art, which
makes it easy to defend.

---

## 5. Legal and compliance

> Again: not legal advice. This is a briefing to make your counsel conversation efficient.

### 5.1 Your structure is the good news, and the record supports it

The distinction regulators have actually enforced on is **house-banked versus peer-funded**, and
you are on the right side of it by design.

The pick'em DFS sector spent 2024–2026 being pushed off against-the-house products:

- Florida's Gaming Control Commission issued cease-and-desist letters to Underdog Sports,
  PrizePicks and Betr; both PrizePicks and Underdog subsequently **resumed operating in Florida
  with new peer-to-peer formats** (PrizePicks "Arena," Underdog "Pick 'Em Champions"), on the
  stated basis that "players compete against each other rather than betting against the house."
- PrizePicks discontinued against-the-house pick'em in California and moved exclusively to
  peer-to-peer Arena, ahead of an expected Attorney General opinion.
- Arkansas ordered PrizePicks and Underdog to stop offering player-prop-style products.

The pattern is unambiguous: **the peer-funded pot with a transparent rake and no house
counterparty is the structure that survived.** You built that on purpose. Protect it — and note
that this is a concrete, citable reason to refuse house-guaranteed pots (§3.2), not just a
cautious instinct.

**The caveat that matters:** California's expected AG opinion was reported as negative on *all*
DFS offerings, "including both against-the-house and peer-to-peer pick'em." Peer-to-peer is a
much better position, not a safe harbour. And your product is arguably *further* from a player
prop than DFS pick'em is, because the subject of the contest is the entrant's own play rather
than a third party's — an entrant with agency over the outcome is the core of every
skill-predominance test. Make that argument explicitly in the memo you commission; it is your
strongest one and it is stronger than PrizePicks'.

### 5.2 The state list

Your 14 excluded states (AZ, AR, CT, DE, FL, IN, LA, MD, MN, MT, SC, SD, TN, WY) are more
conservative than the industry norm, which is fine. For calibration:

- **Players' Lounge** (peer-to-peer esports wagering — your closest structural analogue)
  restricts 12: AZ, AR, CT, DE, FL, IN, LA, MD, MT, SC, SD, TN. You add MN and WY.
- **Skillz** excludes AZ, AR, CT, DE, LA, MT, SC, SD, TN, plus ME and IN where playing cards are
  involved — notably **not** FL or MD.

The three legal tests your counsel will apply: **dominant factor** (skill must predominate —
most states), **material element** (chance must not play a material role — roughly eight
states), and **any chance** (most restrictive). Skillz's public legal framing is a useful
template for the argument structure: gambling requires prize + consideration + chance, and the
defence is on the chance prong.

Two nuances worth raising with counsel:

- **Florida's carve-out language** is unusually specific: legal skill competitions require that
  "the prize is not made up of entry fees, the prize does not vary by the entry fees collected,
  the operator does not compete for the prize, and the prize is announced in advance." Your
  peer-funded pot **fails the first two prongs by construction** — the pot *is* the entry fees
  and it *does* vary with them. That is why FL is on your list and it should stay there. But
  note this cuts the other way too: the peer-funded structure that protects you against the
  house-banked critique is the same structure that fails Florida's contest carve-out. Your
  counsel needs to know you understand this tension.
- **A prize pool made of entry fees is the fact that most often converts a "contest" into
  "gambling"** under state statutes. Skillz's answer is that skill predominance defeats the
  chance prong regardless. Yours should be the same, and your strongest evidence for it is —
  again — **the calibration curve**. "Realised outcomes match our skill model to within 2
  percentage points across 5,000 contests" is an empirical demonstration that skill predominates.
  That is a legal argument, not just a technical one, and it may be the single most valuable
  artifact you can build.

### 5.3 The geo-fence bug

`excluded_states` reading an empty feature flag and failing **open** — every state allowed on a
fresh database — while the code comment claims it fails closed, is the worst single item in this
document from a diligence perspective. It is a one-line fix and it will be found. Fix it today,
add a test that asserts a fresh database blocks all 14 states, and add a startup assertion that
refuses to boot in `ENV=prod` if the excluded list is empty.

While you're there: **state-of-residence attestation is not geolocation.** Every operator in
this space geolocates at the point of entry (IP + device signals, or a vendor like GeoComply).
Self-attested residence is a policy, not a control, and "our geo-fence is a text field the user
fills in" is a bad sentence in a diligence call.

### 5.4 The before-real-money list

- **State-by-state legal opinion.** Investors want the memo, not your reasoning. Budget
  $25–60k and 6–10 weeks with a gaming-law firm (Ifrah, Walters, Fox Rothschild's gaming group
  are the names that come up in this sector). Start this now — it is the longest-lead item on
  your entire roadmap and it gates the launch, not the demo.
- **Geolocation vendor**, not attestation.
- **KYC/AML at withdrawal.** Your `kyc_live` flag + `kyc_status` column + $500 cumulative-entry
  hook is the right shape. Persona, Veriff and Jumio all do this; the integration is ~2 weeks.
  Your guard that flipping the flag with no live provider raises at the resolver is good design
  — say that out loud in diligence, it's the kind of detail that builds trust.
- **Age verification.** 18+ almost everywhere, **21+ in a handful of states**. Your
  attestation-only gate is not sufficient at real money.
- **Payments + tax.** 1099-MISC at $600 in net winnings is the threshold you'll need to handle.
  This is a real operational burden people underestimate.
- **Responsible gaming.** Your daily loss cap, entry caps, concurrency cap, 24-hour delay on
  raising a limit versus instant lowering, and `POST /me/self-exclude` are genuinely above what
  most pre-launch products have. **Lead with this in the investor conversation** — it signals you
  understand the regulatory frame, and it costs you nothing to say.
- **Dispute flow + published rules.** You have the polymorphic dispute model; you need the
  published contest rules that disputes get adjudicated against.

---

## 6. The demo, and the one thing that must exist before it

The advisor is right and I won't belabour it: **you have never collected a CS2 match in
production.** `last_code_at` is null. Everything in §2 is unverifiable until that changes,
because you cannot calibrate against outcomes you have never observed.

The critical path is short:

1. **Fix the sidecar health shape.** `gc_client.health()` returning an identical response for
   "up-but-unattached" and "unreachable," with the router discarding the `detail` field that
   distinguishes them, is why you've been staring at `ready:false` for three days without
   knowing which failure it is. Surface `detail`, then page on it.
2. **Get the sidecar off one process and one Steam account** (§1.4). Three accounts, rotating,
   health-checked, no other Steam surface.
3. **Fix the prior-wipe bug.** `linking_service.bind()` and `refresh()` both call
   `metric_models_service.bootstrap()`, which rebuilds from stored matches — of which there are
   zero — writing n=0 and blowing away the n=3 seed that only the Steam OpenID callback writes.
   This is why refreshing a linked account makes Solo Pools say "No pools on this game yet."
4. **Fix `_derived()`** to use `total_kills_headshot` and `total_matches_played` (§2.8).
5. **One real end-to-end settlement on video.** Real Steam account, real Premier match,
   collected automatically off the chain, graded, money moved. No hands.
6. **Alerting.** A stalled sidecar or a chain collecting nothing is currently invisible without
   manually querying an endpoint. Page on: worker heartbeat stale > 120s, sidecar `ready:false`
   > 5 min, zero share codes collected in 6 hours across all users, settlement paused,
   reconciliation breach.

Keep `force_settle` as a rehearsed fallback, and if you use it live, say so. An investor who
catches you not saying so has learned something much worse than that your demo broke.

### 6.1 The Repeat.gg question, and your answer

Repeat.gg announced its wind-down on **13 May 2026**, with tournaments concluding by June 2026,
after more than a decade of operation. PlayStation-owned, 2M+ users. A sharp investor will lead
with it.

Your answer falls out of your architecture and it's a good one:

> Repeat was leaderboard-tournament based — you grind for a top-N finish in a bracket. That
> structurally rewards volume and elite players, so the median player loses consistently and
> churns. Our personal-bar model means the median player has a real ~35% shot, because they're
> competing against their own baseline rather than against the best player in the bracket. Our
> retention curve should look structurally different, and we can show you the calibration data
> that proves the bar is where we say it is.

Two things to add:

- **Their community is homeless right now.** Users had a six-month withdrawal window from 13
  May; that is an acquisition event with a known end date. If you're going to launch in 2026,
  the calendar argues for sooner.
- **Be honest that PlayStation cited a "shift in priorities," not unit economics.** Over-reading
  the shutdown as a market verdict is a trap; a sharp investor will know the difference and will
  respect you for making the distinction.

---

## 7. The calibration harness — build this, it is your best slide

This is cheap, it touches no production code path, and it is simultaneously your technical
credibility, your pot-math correctness check, your free-option detector, and (per §5.2) an input
to your legal argument that skill predominates.

### 7.1 What to record

At bar placement, snapshot into an immutable `bar_predictions` row:

```
contest_id, user_id, game, mode, metric, difficulty, entry_bucket
mu_hat, sigma_hat, sigma_effective, n_raw, n_eff, prior_used, prior_weight
bar, p_predicted, distribution_family, positive_flag, comparison_op
model_version, placed_at
```

At settlement, append: `realised_value, cleared (bool), match_id, rounds_played, mode_actual,
kills_total, settled_at, outcome ∈ {cleared, missed, refunded_no_match, cancelled}`.

`model_version` matters more than it looks — without it you cannot tell a real calibration
improvement from a population shift.

### 7.2 What to compute

**Reliability diagram.** Bin predictions by `p_predicted` (deciles, or the three difficulty
tiers). Plot predicted vs realised with Wilson 95% intervals. Perfect calibration is the
diagonal. This is the chart.

**Expected calibration error.** `ECE = Σ_b (n_b/N)·|realised_b − predicted_b|`. One number,
reportable, trendable. Target: under 3pp.

**Brier score with the Murphy decomposition.** `BS = reliability − resolution + uncertainty`.
The reliability term is calibration; the resolution term is how much your model *discriminates*.
Report both — a well-calibrated model with zero resolution is a model that always predicts the
base rate, and you want to be able to prove you're not that.

**Slice everything.** By metric × difficulty × mode × `n_eff` bucket × prior-used. §2.3 shows the
aggregate can look calibrated while every slice is wrong.

**Completion-conditional calibration.** Compute realised clear rate over players who *completed*
separately from the modelled population. The gap between them **is** the free-option value
(§4.1), measured rather than assumed. If this gap is large, raise `k` for everyone (§4.2 #2).

### 7.3 How much data you need

To detect a miscalibration at 80% power, α=0.05:

| Claimed | True | n per cell |
| --- | --- | --- |
| 35% | 45% | **184** |
| 35% | 40% | 726 |
| 20% | 28% | 211 |
| 20% | 25% | 528 |
| 10% | 16% | 224 |
| 10% | 13% | 843 |

Half-width of a 95% Wilson interval on a 35% realised rate:

| n | ± |
| --- | --- |
| 30 | 16.0pp |
| 100 | 9.2pp |
| 300 | 5.4pp |
| 1,000 | 3.0pp |
| 3,000 | 1.7pp |

**Practical read:** ~200 settled contests per cell catches a gross error; ~800 catches a
meaningful one. Across 3 metrics × 3 difficulties that's roughly **1,800 settled contests for a
credible first curve, 7,000 for a tight one.** At a 24-hour window and any realistic launch
traffic, that is months — which is another argument for the shorter play window in §4.2, and a
reason to **seed the harness with backtest data now**: run your bar-placement code over
historical match sequences from public CS2 data and score it retrospectively. You do not need a
single wager to produce a first calibration curve, and you could have one in a week.

That backtest is, I think, the highest-value thing you could build before the investor meeting
after the end-to-end settlement itself. It answers "what's defensible here?" with a chart rather
than an assertion.

---

## 8. Consolidated recommendations

### Do this week (all cheap, all high-magnitude)

| Item | § | Why |
| --- | --- | --- |
| Fix the geo-fence fail-open | 5.3 | One line. Worst diligence item in this doc |
| Fix sidecar health `detail` shape, then page on it | 6 | You've been blind for three days |
| Fix the CS2 prior wipe on `refresh()` | 6 | Real users get "no pools on this game yet" |
| Fix `_derived()` to use the totals Steam already returns | 2.8 | Free signal; current bars are unclearable |
| Add a ≥12-kill floor to headshot-% markets | 2.2 | Closes a 10× exploit |
| Make `≥` vs `>` explicit and consistent in grading, clear-prob and the card | 2.5 | 27% relative error, five minutes |
| Change `cs2_kd_ratio` increment 0.05 → 0.01; delete `cs2_adr` | 2.7 | ±3.7pp of quoted accuracy |
| Instrument fill rate, time-to-fill, expired-unmatched (bots excluded) | 3.4 | You cannot see your own market |
| Start the legal-opinion engagement | 5.4 | Longest lead item on the roadmap |

### Do before the investor demo (2–4 weeks)

| Item | § |
| --- | --- |
| One real end-to-end CS2 settlement, on video, no hands | 6 |
| Sidecar fleet: ≥3 accounts, rotating, health-checked, no other Steam surface | 1.4 |
| Split Premier / Competitive / Wingman into separate models and markets | 2.3 |
| Student-t predictive bar placement | 2.6 |
| Backtested calibration curve from public CS2 data | 7.3 |
| Alerting on settlement stalls, chain silence, reconciliation breach | 6 |
| A 30-second "how your bar is set" explainer | — |
| Written answer to the Repeat.gg question and the Steam-ToS question | 6.1, 1.4 |

### Do before real money

| Item | § |
| --- | --- |
| State-by-state legal opinion in hand | 5.4 |
| Geolocation vendor replacing self-attested residence | 5.3 |
| KYC/AML at withdrawal; 21+ handling where required; 1099 flow | 5.4 |
| Fill window separated from play window (24h fill / ~45min play) | 4.2 |
| Bucket collapse: CS2-only, pro-rated entry, weighted-payout difficulty | 3.2 |
| Asymmetric EWMA (`hl_up=10`, `hl_down=40`) + bar-velocity floor | 4.3 |
| Completion-rate risk detector | 4.2 |
| Live calibration harness with ≥200 settled contests per cell | 7 |
| Delete `test_opponents.py` | — |

### Explicitly do not do

| Item | Why |
| --- | --- |
| Add League / Valorant / TFT / any Riot title | Riot Developer Policies: "Your product cannot feature betting or gambling functionality" |
| Add Clash Royale / Brawl Stars / any Supercell title | ToS bans wagering on your own matches, fee or no fee |
| Add Rocket League, Apex, Marvel Rivals | No official verifiable match-history feed |
| Add any fourth vertical before CS2 fill rate > 80% | §3.1 — you are dividing an empty market |
| House-guaranteed pots | Converts you into a counterparty; that is the exact structure regulators moved against |
| Grade a no-show as a loss | "You cannot lose by not playing" is worth more than the leakage |
| Ship PUBG at launch | Dev-ToS exposure + liquidity dilution, removed in one commit |

---

## Sources

- [Riot Games Developer Policies (General)](https://support-developer.riotgames.com/hc/en-us/articles/22698591841939-General-Policies)
- [Supercell Terms of Service](https://supercell.com/en/terms-of-service/)
- [Steam Subscriber Agreement](https://store.steampowered.com/subscriber_agreement/)
- [Steam Web API Terms of Use](https://steamcommunity.com/dev/apiterms)
- [PUBG Developer API Terms of Use](https://developer.pubg.com/tos?locale=en)
- [Lichess Terms of Service](https://lichess.org/terms-of-service)
- [Chess.com Published-Data API](https://www.chess.com/announcements/view/published-data-api)
- [Rocket League Stats API](https://www.rocketleague.com/developer/stats-api)
- [osu!api documentation](https://osu.ppy.sh/wiki/en/osu%21api)
- [Marvel Rivals API (third-party)](https://marvelrivalsapi.com/)
- [TrueSkill 2: An improved Bayesian skill rating system — Minka, Cleven, Zaykov (Microsoft Research)](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/trueskill2.pdf)
- [Batching and Greedy Policies: How Good Are They in Dynamic Matching? (Georgia Tech)](https://bpb-us-e1.wpmucdn.com/sites.gatech.edu/dist/7/1474/files/2025/09/Dynamic_nbip_matching_v4.pdf)
- [Evaluating probabilistic classifiers: reliability diagrams and score decompositions (arXiv 2008.03033)](https://arxiv.org/pdf/2008.03033)
- [US 9,349,249 B2 — Anti-sandbagging in head-to-head gaming (Gamblit Gaming LLC)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9349249)
- [PrizePicks abandons against-the-house pick'em in California (SBC Americas)](https://sbcamericas.com/2025/07/02/prizepicks-california-p2p-arena-switch/)
- [PrizePicks, Underdog resume Florida operations with new formats (The Capitolist)](https://thecapitolist.com/prizepicks-underdog-fantasy-resume-operations-in-florida-with-new-legal-gaming-formats/)
- [PrizePicks, Underdog ordered to leave Arkansas over player props (Legal Sports Report)](https://www.legalsportsreport.com/167246/prizepicks-underdog-ordered-to-leave-arkansas-for-offering-player-props/)
- [Florida regulator issues C&Ds to Underdog, PrizePicks, Betr (Gaming America)](https://gamingamerica.com/news/8713/florida-regulator-issues-cease-and-desist-letters-to-underdog-sports-prizepicks-and-betr)
- [Which States Allow Skill Gaming? (Walters Law Group)](https://www.firstamendment.com/list-states-skill-gaming-allowed-prohibited/)
- [The Legality of Skill Gaming (Skillz)](https://docs.skillz.com/docs/29.2.35/legal-skillz/)
- [Players' Lounge restricted locations](https://www.playerslounge.com/support/restricted-locations)
- [Repeat is shutting down: what this means for users](https://support.repeat.gg/hc/en-us/articles/49769807896859-Repeat-is-shutting-down-What-this-means-for-users)
- [CS2 Rank Distribution 2026 — Premier ratings & percentiles (CSDB.gg, Leetify data)](https://csdb.gg/rank-distribution/)
