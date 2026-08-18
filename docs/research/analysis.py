#!/usr/bin/env python3
"""
Money Match -- reproducible analysis behind MONEYMATCH_RESEARCH.md

    pip install numpy scipy
    python3 analysis.py

Every table in the research document is produced by one of the sections below.
Seeds are fixed, so numbers reproduce exactly.

Sections
  1  Headshot %: normal bar vs the true beta-binomial process
  1b Headshot %: the deliberate low-kill exploit          (doc 2.2)
  2  Kills: normal vs negative binomial vs >= / >         (doc 2.5)
  3  Round normalisation: variance decomposition          (doc 2.4)
  3b Round normalisation: sensitivity to rounds<->kpr corr(doc 2.4)
  4  Mode pollution: Wingman + Premier in one model       (doc 2.3)
  5  Liquidity: P(pool fills inside TTL) by bucket count  (doc 3.1)
  6  The free option: value of "only play when sharp"     (doc 4.1)
  7  Sandbagging under EWMA half-life 10                  (doc 4.3)
  8  Calibration harness: sample sizes                    (doc 7.3)
  9  Parameter uncertainty + the Student-t fix            (doc 2.6)
 10  Bar quantisation: pp of clear prob per increment     (doc 2.7)
 11  What hierarchical shrinkage on sigma actually buys   (doc 2.6)
 12  Decoupling the mu / sigma half-lives                 (doc 2.6)
"""

import math

import numpy as np
from scipy import stats
from scipy.stats import multivariate_normal as mvn
from math import sqrt

K_EASY, K_MED, K_HARD = 0.385, 0.842, 1.282
DIFFS = [("easy", K_EASY), ("medium", K_MED), ("hard", K_HARD)]


def ewma(values, hl=10.0):
    """Recency-weighted mean and (population) sd -- mirrors metric_models_service."""
    v = np.asarray(values, float)
    n = len(v)
    i = np.arange(n)
    w = 0.5 ** ((n - 1 - i) / hl)
    mu = (w * v).sum() / w.sum()
    sd = sqrt((w * (v - mu) ** 2).sum() / w.sum())
    return mu, sd


def n_effective(n, hl=10.0):
    i = np.arange(n)
    w = 0.5 ** ((n - 1 - i) / hl)
    return w.sum() ** 2 / (w ** 2).sum()


def rnd(x, inc):
    return round(x / inc) * inc


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------- 0
rule("0. Claimed clear rates from POOL_DIFFICULTY_K")
for name, k in DIFFS:
    print(f"   {name:7s} k={k:.3f}  1-Phi(k) = {(1 - stats.norm.cdf(k)) * 100:5.2f}%")


# ---------------------------------------------------------------- 1
rule("1. HEADSHOT %: normal bar vs the true beta-binomial process   [doc 2.2]")
rng = np.random.default_rng(7)


def gen_hs(n, mean_k=17.0, var_k=40.0, p=0.42, conc=60.0):
    """Per-match kills ~ NegBinom; per-match true hs rate ~ Beta; headshots ~ Binom."""
    r = mean_k ** 2 / (var_k - mean_k)
    pr = r / (r + mean_k)
    K = stats.nbinom.rvs(r, pr, size=n, random_state=rng) + 1
    q = rng.beta(p * conc, (1 - p) * conc, size=n)
    H = rng.binomial(K, q)
    return 100.0 * H / K, K


hist, _ = gen_hs(50)
mu, sd = ewma(hist)
sd_eff = max(sd, 2 * 1.0)
print(f"   EWMA over 50 matches: mu={mu:.2f}  sigma={sd:.2f} (effective {sd_eff:.2f})")
fut, futK = gen_hs(400_000)
for name, k in DIFFS:
    bar = max(0.0, rnd(mu + k * sd_eff, 1.0))
    quoted = 1 - stats.norm.cdf((bar - mu) / sd_eff)
    real = (fut >= bar).mean()
    print(f"   {name:7s} bar={bar:5.1f}  quoted={quoted*100:5.2f}%  "
          f"realised={real*100:5.2f}%  ratio={real/quoted:4.2f}x")

bar_h = max(0.0, rnd(mu + K_HARD * sd_eff, 1.0))
print(f"\n   realised clear rate at the HARD bar ({bar_h:.0f}%), split by match kill count:")
for lo, hi in [(1, 7), (8, 14), (15, 21), (22, 60)]:
    m = (futK >= lo) & (futK <= hi)
    print(f"     kills {lo:2d}-{hi:2d}: n={m.sum():7d}  clear={100*(fut[m] >= bar_h).mean():5.2f}%")
print("   -> variance of a proportion is p(1-p)/K. The player controls K.")


# ---------------------------------------------------------------- 1b
rule("1b. HEADSHOT %: the deliberate low-kill exploit   [doc 2.2]")
for bar in [55, 60, 65]:
    print(f"   bar = {bar}%")
    for kills, p, lbl in [(17, 0.42, "normal 17-kill game, 42% aim"),
                          (4, 0.42, "4 kills, 42% aim"),
                          (4, 0.62, "4 kills, Deagle/AWP-only (62%)"),
                          (2, 0.62, "2 kills, Deagle-only (62%)")]:
        need = int(np.ceil(bar / 100 * kills))
        pr = 1 - stats.binom.cdf(need - 1, kills, p)
        print(f"      {lbl:32s} -> P(clear) = {pr*100:5.1f}%")


# ---------------------------------------------------------------- 2
rule("2. KILLS: normal vs negative binomial vs >= / >   [doc 2.5]")
mu_k, var_k = 17.0, 36.0
r = mu_k ** 2 / (var_k - mu_k)
pr_ = r / (r + mu_k)
print(f"   mu={mu_k}  sigma={sqrt(var_k)}  overdispersion index var/mu = {var_k/mu_k:.2f}")
for name, k in DIFFS:
    bar = rnd(mu_k + k * sqrt(var_k), 1.0)
    quoted = 1 - stats.norm.cdf((bar - mu_k) / sqrt(var_k))
    nb_ge = 1 - stats.nbinom.cdf(bar - 1, r, pr_)
    nb_gt = 1 - stats.nbinom.cdf(bar, r, pr_)
    print(f"   {name:7s} bar={bar:4.0f}  quoted(normal)={quoted*100:5.2f}%   "
          f"NB P(X>=bar)={nb_ge*100:5.2f}%   NB P(X>bar)={nb_gt*100:5.2f}%")
print("   -> the >= vs > gap (27% relative at hard) is larger than the NB gap (22%).")


# ---------------------------------------------------------------- 3
rule("3. ROUND NORMALISATION: variance decomposition   [doc 2.4]")
rounds = np.array([13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 27, 30])
w = np.array([2, 4, 6, 8, 10, 12, 13, 13, 12, 10, 8, 6, 3, 1], float)
w /= w.sum()
ER = (rounds * w).sum()
VR = ((rounds - ER) ** 2 * w).sum()
kpr_mu, kpr_sd, per_round_sd = 0.74, 0.16, 0.85
v_within = ER * per_round_sd ** 2
v_form = ER ** 2 * kpr_sd ** 2
v_rounds = VR * kpr_mu ** 2
tot = v_within + v_form + v_rounds
EK = kpr_mu * ER
print(f"   E[rounds]={ER:.1f}  sd(rounds)={sqrt(VR):.2f}   E[kills]={EK:.1f}  sd(kills)={sqrt(tot):.2f}")
print(f"     within-match round noise : {v_within:6.1f}  ({100*v_within/tot:4.1f}%)")
print(f"     player form (kpr)        : {v_form:6.1f}  ({100*v_form/tot:4.1f}%)")
print(f"     ROUND COUNT              : {v_rounds:6.1f}  ({100*v_rounds/tot:4.1f}%)")


# ---------------------------------------------------------------- 3b
rule("3b. ROUND NORMALISATION: sensitivity to corr(rounds, kpr)   [doc 2.4]")
rng = np.random.default_rng(3)
N = 400_000
for rho in [0.0, -0.3, -0.5, -0.7]:
    z1 = rng.normal(size=N)
    z2 = rho * z1 + sqrt(1 - rho ** 2) * rng.normal(size=N)
    R = np.clip(np.round(19.5 + 3.2 * z1), 13, 30)
    kpr_form = 0.74 + 0.16 * z2
    kills = rng.poisson(np.clip(kpr_form, 0.05, None) * R)
    rel_kills = kills.std() / kills.mean()
    kpr_obs = kills / R
    rel_kpr = kpr_obs.std() / kpr_obs.mean()
    print(f"   corr={rho:+.1f}  rel-sd kills={100*rel_kills:5.1f}%   "
          f"rel-sd kills/round={100*rel_kpr:5.1f}%   change={100*(rel_kpr/rel_kills-1):+5.1f}%")
print("   -> CS2 is the negative-correlation case: stomps are SHORT and high-kpr,")
print("      grinds are LONG and low-kpr, so the two partially cancel in total kills.")


# ---------------------------------------------------------------- 4
rule("4. MODE POLLUTION: Wingman + Premier in one cs2_kills model   [doc 2.3]")
prem = rng.normal(17, 5.5, N // 2)
wing = rng.normal(9.5, 3.8, N // 2)
mix = np.concatenate([prem, wing])
mu, sd = mix.mean(), mix.std()
print(f"   pooled mu={mu:.2f} sigma={sd:.2f}   (Premier 17/5.5, Wingman 9.5/3.8, 50/50)")
for name, k in DIFFS:
    bar = round(mu + k * sd)
    q = 1 - stats.norm.cdf((bar - mu) / sd)
    pp, pw = (prem >= bar).mean(), (wing >= bar).mean()
    print(f"   {name:7s} bar={bar:3d}  quoted={q*100:5.2f}%  |  Premier: {pp*100:5.2f}%   "
          f"Wingman: {pw*100:5.2f}%   mispricing={pp/q:4.2f}x")


# ---------------------------------------------------------------- 5
rule("5. LIQUIDITY: P(a 3-seat pool fills inside the TTL)   [doc 3.1]")


def p_fill(lam_per_day, ttl_days=1.0, need=2):
    lt = lam_per_day * ttl_days
    return 1 - sum(math.exp(-lt) * lt ** i / math.factorial(i) for i in range(need))


q_accept = 0.5
print(f"   Poisson arrivals per bucket; composition acceptance q={q_accept}; TTL 24h; min room 3")
print(f"   {'daily joins':>11} | " + " | ".join(f"B={b:>3}  fill    wait" for b in [108, 36, 12, 4]))
for D in [50, 200, 1000, 5000, 20000]:
    cells = []
    for B in [108, 36, 12, 4]:
        lam = D / B * q_accept
        cells.append(f"{100*p_fill(lam):8.1f}% {2/lam*24:7.1f}h")
    print(f"   {D:>11} | " + " | ".join(cells))


# ---------------------------------------------------------------- 6
rule("6. THE FREE OPTION: value of 'only play when sharp'   [doc 4.1]")
print("   X~N(0,1) is match performance; bar at z_k. Player sees S = rho*X + sqrt(1-rho^2)*eps")
print("   BEFORE queueing, plays only when S>0, else lets the window expire for a full refund.")
for name, zk, base in [("easy", K_EASY, 0.35), ("medium", K_MED, 0.20), ("hard", K_HARD, 0.10)]:
    line = f"   {name:7s} (base {base*100:4.1f}%):"
    for rho in [0.3, 0.5, 0.7]:
        R = np.array([[1, rho], [rho, 1]])
        p_joint = mvn(mean=[0, 0], cov=R).cdf([-zk, 0.0])   # = P(X>zk, S>0) by symmetry
        p_sel = p_joint / 0.5
        line += f"   rho={rho}: {p_sel*100:5.1f}% ({p_sel/base:4.2f}x)"
    print(line)


def pool_ev(p_self, p_other, N=4, entry=2500, rake_bps=1000):
    """Cents. No-clear outcome refunds everyone (so no rake is taken)."""
    pot = N * entry
    dist = pot - pot * rake_bps // 10000
    ev_pay = sum(math.comb(N - 1, j) * p_other ** j * (1 - p_other) ** (N - 1 - j)
                 * p_self * dist / (j + 1) for j in range(N))
    p_any = 1 - (1 - p_self) * (1 - p_other) ** (N - 1)
    ev = ev_pay - entry * p_any
    return ev / 100.0, ev / entry


print("\n   EV in a 4-handed $25 pool, 10% rake:")
for lbl, ps, po in [("everyone honest (all 35.0%)   ", 0.350, 0.350),
                    ("shark rho=0.5 (49.2%) vs field", 0.492, 0.350),
                    ("shark rho=0.7 (57.3%) vs field", 0.573, 0.350),
                    ("casual in a room with a shark ", 0.350, 0.492)]:
    ev, roi = pool_ev(ps, po)
    print(f"     {lbl}: EV = ${ev:+6.2f}/contest   ROI = {roi*100:+6.1f}%")
ev, _ = pool_ev(0.35, 0.35)
print(f"   conservation check: 4 x {ev:+.2f} = {4*ev:+.2f}  (= the rake actually collected)")


# ---------------------------------------------------------------- 7
rule("7. SANDBAGGING under EWMA half-life 10   [doc 4.3]")
true_mu, true_sd = 17.0, 5.5
hist = list(np.random.default_rng(5).normal(true_mu, true_sd, 50))
m0, s0 = ewma(hist)
print(f"   honest: mu={m0:.2f} sd={s0:.2f} -> hard bar {round(m0 + 1.282*s0)}")
for m in [3, 5, 10, 15, 20]:
    mu, sd = ewma(hist + [4.0] * m)
    sd = max(sd, 2.0)
    bar = round(mu + 1.282 * sd)
    real = 1 - stats.norm.cdf((bar - true_mu) / true_sd)
    print(f"   after {m:2d} tanked matches: mu={mu:5.2f} sd={sd:5.2f} bar={bar:3d}  "
          f"TRUE clear = {real*100:5.1f}% (quoted 10%) = {real/0.10:.1f}x")
print(f"   z-test on 3 tanked matches: z = (4-17)/(5.5/sqrt(3)) = {(4-17)/(5.5/sqrt(3)):.2f}")


# ---------------------------------------------------------------- 8
rule("8. CALIBRATION HARNESS: sample sizes   [doc 7.3]")


def n_needed(p0, p1, alpha=0.05, power=0.80):
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    return math.ceil((za * sqrt(p0 * (1 - p0)) + zb * sqrt(p1 * (1 - p1))) ** 2 / (p1 - p0) ** 2)


print("   n per cell to detect a miscalibration at 80% power, alpha=0.05:")
for p0, p1 in [(0.35, 0.45), (0.35, 0.40), (0.20, 0.28), (0.20, 0.25), (0.10, 0.16), (0.10, 0.13)]:
    print(f"     claimed {p0*100:4.0f}%  true {p1*100:4.0f}%  ->  n = {n_needed(p0, p1):5d}")
print("   half-width of a 95% Wilson CI on a 35% realised rate:")
for n in [30, 100, 300, 1000, 3000]:
    lo, hi = stats.binomtest(int(round(0.35 * n)), n).proportion_ci(0.95, method="wilson")
    print(f"     n={n:5d}:  35% +/- {100*(hi-lo)/2:.1f}pp")


# ---------------------------------------------------------------- 9
rule("9. PARAMETER UNCERTAINTY, and the Student-t fix   [doc 2.6]")
for n, hl in [(20, 10), (50, 10), (50, 20), (100, 10)]:
    print(f"   window n={n:3d}, half-life={hl:2d}:  n_eff = {n_effective(n, hl):5.1f}")
print("\n   Monte-Carlo, true process EXACTLY N(17, 5.5), 4000 simulated players,")
print("   bootstrap of 50 matches, EWMA hl=10:")
rng = np.random.default_rng(21)


def sim(mode, trials=4000):
    out = {}
    for name, k, claim in [("easy", K_EASY, .35), ("medium", K_MED, .20), ("hard", K_HARD, .10)]:
        reals = []
        for _ in range(trials):
            s = rng.normal(17, 5.5, 50)
            i = np.arange(50)
            w = 0.5 ** ((49 - i) / 10.0)
            neff = w.sum() ** 2 / (w ** 2).sum()
            mu = (w * s).sum() / w.sum()
            sd = sqrt((w * (s - mu) ** 2).sum() / w.sum())
            if mode == "plugin":
                sd = max(sd, 2.0)
                bar = round(mu + k * sd)
            else:
                sd = max(sd * sqrt(neff / (neff - 1)), 2.0)
                tq = stats.t.ppf(1 - claim, df=max(neff - 1, 2))
                bar = round(mu + tq * sd * sqrt(1 + 1 / neff))
            reals.append(1 - stats.norm.cdf((bar - 17) / 5.5))
        out[name] = (np.array(reals), claim)
    return out


for mode, label in [("plugin", "PLUG-IN NORMAL (today)"), ("t", "STUDENT-T PREDICTIVE (fix)")]:
    print(f"\n   {label}")
    for name, (r, claim) in sim(mode).items():
        print(f"     {name:7s} target={claim*100:4.1f}%  realised={r.mean()*100:5.2f}%  "
              f"sd={r.std()*100:4.2f}pp  10-90=[{np.percentile(r,10)*100:4.1f}%,"
              f"{np.percentile(r,90)*100:4.1f}%]")
print("\n   bar = mu + t_{n_eff-1}(1-p) * sigma_unbiased * sqrt(1 + 1/n_eff)")


# ---------------------------------------------------------------- 10
rule("10. BAR QUANTISATION: pp of clear probability per increment   [doc 2.7]")
for metric, sd, inc in [("cs2_kd_ratio", 0.25, 0.05), ("cs2_kd_ratio (proposed)", 0.25, 0.01),
                        ("cs2_kills", 5.5, 1.0), ("cs2_headshot_pct", 12.0, 1.0),
                        ("cs2_kills_per_round", 0.25, 0.01)]:
    for lbl, k in [("easy", K_EASY), ("hard", K_HARD)]:
        dp = stats.norm.pdf(k) / sd * inc
        print(f"   {metric:24s} {lbl:5s}: 1 increment = {dp*100:5.2f}pp  "
              f"-> rounding alone = +/-{dp*50:4.2f}pp")


# ---------------------------------------------------------------- 11
rule("11. WHAT HIERARCHICAL SHRINKAGE ON SIGMA BUYS   [doc 2.6]")
rng = np.random.default_rng(99)
POP_SD = 5.5
print("   population: true mu ~ N(15,3), true sigma ~ Gamma(mean 5.5, sd 1.2); target 10%")


def run_shrink(mode, w_prior=0.0, trials=6000):
    reals = []
    for _ in range(trials):
        tm = rng.normal(15, 3)
        ts = max(rng.gamma((5.5 / 1.2) ** 2, 1.2 ** 2 / 5.5), 1.5)
        s = rng.normal(tm, ts, 50)
        i = np.arange(50)
        wt = 0.5 ** ((49 - i) / 10.0)
        neff = wt.sum() ** 2 / (wt ** 2).sum()
        mu = (wt * s).sum() / wt.sum()
        sd = sqrt((wt * (s - mu) ** 2).sum() / wt.sum() * neff / (neff - 1))
        if mode == "shrunk":
            sd = sqrt((neff * sd ** 2 + w_prior * POP_SD ** 2) / (neff + w_prior))
        sd = max(sd, 2.0)
        if mode == "plugin":
            bar = round(mu + 1.282 * sd)
        else:
            tq = stats.t.ppf(0.90, df=max(neff - 1, 2))
            bar = round(mu + tq * sd * sqrt(1 + 1 / neff))
        reals.append(1 - stats.norm.cdf((bar - tm) / ts))
    r = np.array(reals)
    return r.mean(), r.std(), np.abs(r - 0.10).mean()


for lbl, mode, wp in [("plug-in normal (today)", "plugin", 0),
                      ("t-predictive", "t", 0),
                      ("t-predictive + shrink w=10", "shrunk", 10),
                      ("t-predictive + shrink w=25", "shrunk", 25),
                      ("t-predictive + shrink w=60", "shrunk", 60)]:
    m, s, mae = run_shrink(mode, wp)
    print(f"   {lbl:28s} mean={m*100:5.2f}%  sd={s*100:4.2f}pp  MAE={mae*100:4.2f}pp")
print("   MAE = mean |realised - target|. THIS is the headline calibration metric.")


# ---------------------------------------------------------------- 12
rule("12. DECOUPLING THE mu / sigma HALF-LIVES   [doc 2.6]")
rng = np.random.default_rng(1234)
print("   true process: mu is a random walk (sd 0.35/match) around 15; sigma fixed at 5.5")


def run_hl(hl_mu, hl_sd, window, trials=6000):
    reals = []
    for _ in range(trials):
        n = window
        drift = np.cumsum(rng.normal(0, 0.35, n))
        tmu, ts = 15 + drift, 5.5
        s = rng.normal(tmu, ts)
        i = np.arange(n)
        wm = 0.5 ** ((n - 1 - i) / hl_mu)
        ws = 0.5 ** ((n - 1 - i) / hl_sd)
        mu = (wm * s).sum() / wm.sum()
        m2 = (ws * s).sum() / ws.sum()
        neff = ws.sum() ** 2 / (ws ** 2).sum()
        sd = max(sqrt((ws * (s - m2) ** 2).sum() / ws.sum() * neff / (neff - 1)), 2.0)
        tq = stats.t.ppf(0.90, df=max(neff - 1, 2))
        bar = round(mu + tq * sd * sqrt(1 + 1 / neff))
        nxt = 15 + drift[-1] + rng.normal(0, 0.35)
        reals.append(1 - stats.norm.cdf((bar - nxt) / ts))
    r = np.array(reals)
    return r.mean(), r.std(), np.abs(r - 0.10).mean()


print(f"   {'hl_mu':>6} {'hl_sd':>6} {'window':>7}   mean     sd      MAE")
for hm, hs, wd in [(10, 10, 50), (10, 20, 50), (10, 30, 50),
                   (10, 30, 100), (5, 30, 100), (10, 50, 150), (20, 20, 50)]:
    m, s, mae = run_hl(hm, hs, wd)
    print(f"   {hm:6d} {hs:6d} {wd:7d}   {m*100:5.2f}%  {s*100:5.2f}pp  {mae*100:5.2f}pp")

print("\nDone.")
