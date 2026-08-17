#!/usr/bin/env python3
"""
Money Match -- the four metric families, across all four games.
Reproduces every figure in bar-math.html.

    pip install numpy scipy && python3 metric_families.py

PART 1  audits each live metric: fit the normal the way the codebase does,
        then measure what fraction of matches REALLY clear the resulting bar.
PART 2  tests the fixes: lognormal and empirical quantiles for ratios,
        and what a denominator floor does to the headshot exploit.

These are simulations against realistic generative models, NOT measurements of
live traffic. They say what should happen given the modelling choices. Confirm
against real settled contests once the calibration harness exists.
"""
import numpy as np
from scipy import stats
from math import sqrt
rng = np.random.default_rng(42)
K_E, K_M, K_H = 0.385, 0.842, 1.282
N = 300_000

def audit(name, sample, inc=1.0, floor=None):
    """Fit the normal the way the codebase does, then measure the REAL clear rate."""
    mu, sd = sample.mean(), sample.std()
    out=[]
    for lbl,k,claim in [("easy",K_E,.35),("medium",K_M,.20),("hard",K_H,.10)]:
        bar = round((mu + k*sd)/inc)*inc
        if floor is not None: bar = max(bar, floor)
        quoted = 1-stats.norm.cdf((bar-mu)/sd)
        real = (sample >= bar).mean()
        out.append((lbl,bar,quoted,real))
    print(f"\n{name}   mu={mu:.2f} sd={sd:.2f}  skew={stats.skew(sample):+.2f}  P(=0)={100*(sample==0).mean():.1f}%")
    for lbl,bar,q,r in out:
        flag = "  <-- BROKEN" if (r/q>1.25 or r/q<0.8) else ""
        print(f"   {lbl:7s} bar={bar:8.2f}  quoted={q*100:5.2f}%  actual={r*100:5.2f}%  ratio={r/q:4.2f}x{flag}")

print("="*76); print("FAMILY 1 -- COUNTS"); print("="*76)
# CS2 kills: overdispersed count
R = np.clip(np.round(rng.normal(19.5,3.2,N)),13,30)
cs2_kills = rng.poisson(np.clip(rng.normal(0.85,0.18,N),0.05,None)*R)
audit("CS2 kills (Premier)", cs2_kills, inc=1.0)

# PUBG kills: ZERO-INFLATED count -- you die early with 0 kills very often
survived = rng.random(N) > 0.55                      # 55% of games you die early
pubg_kills = np.where(survived, rng.poisson(2.4,N), rng.binomial(1,0.25,N))
audit("PUBG kills", pubg_kills, inc=1.0)

# Chess moves in WON games: positive right-skewed count
chess_moves = np.round(rng.lognormal(np.log(32)-0.5*0.36**2,0.36,N))
audit("Chess moves (won games)", chess_moves, inc=1.0)

print("\n"+"="*76); print("FAMILY 2 -- PROPORTIONS  (the denominator is the problem)"); print("="*76)
q_true = rng.beta(.42*60,(1-.42)*60,N)
cs2_hs = 100*rng.binomial(np.maximum(cs2_kills,1),q_true)/np.maximum(cs2_kills,1)
audit("CS2 headshot %  (denominator ~17 kills)", cs2_hs, inc=1.0)
qp = rng.beta(.20*40,(1-.20)*40,N)
pk = np.maximum(pubg_kills,1)
pubg_hs = 100*rng.binomial(pk,qp)/pk
audit("PUBG headshot % (denominator ~2 kills!)", pubg_hs, inc=1.0)

print("\n"+"="*76); print("FAMILY 3 -- RATIOS  (heavy tails, undefined at zero)"); print("="*76)
deaths = rng.poisson(np.clip(rng.normal(0.85,0.15,N),0.05,None)*R)
kd = cs2_kills/np.maximum(deaths,1)
audit("CS2 K/D (deaths floored at 1)", kd, inc=0.05)
audit("CS2 K/D, finer increment", kd, inc=0.01)
dk,dd,da = rng.poisson(7.5,N), rng.poisson(6.5,N), rng.poisson(13.,N)
kda=(dk+da)/np.maximum(dd,1)
audit("Dota 2 KDA", kda, inc=0.1)

print("\n"+"="*76); print("FAMILY 4 -- RATES  (already normalised: the well-behaved one)"); print("="*76)
gpm = rng.normal(480,95,N)
audit("Dota 2 GPM", gpm, inc=10.0)
kpr = cs2_kills/R
audit("CS2 kills-per-round", kpr, inc=0.01)


print('\n')
deaths=rng.poisson(np.clip(rng.normal(0.85,0.15,N),0.05,None)*R)
kd=cs2_kills/np.maximum(deaths,1)
dk,dd,da=rng.poisson(7.5,N),rng.poisson(6.5,N),rng.poisson(13.,N); kda=(dk+da)/np.maximum(dd,1)
from math import exp
def compare(name,s,inc):
    mu,sd=s.mean(),s.std()
    print(f"\n{name}  (mu={mu:.2f} sd={sd:.2f} skew={stats.skew(s):+.2f})")
    print(f"   {'tier':7s} {'NORMAL bar':>11} {'act':>7} | {'LOGNORM bar':>12} {'act':>7} | {'EMPIRICAL bar':>14} {'act':>7}")
    s2=np.log(np.maximum(s,1e-9)); m_=s2.mean(); sg=s2.std()
    for lbl,k,claim in [("easy",K_E,.35),("medium",K_M,.20),("hard",K_H,.10)]:
        bn=round((mu+k*sd)/inc)*inc
        bl=round(exp(m_+k*sg)/inc)*inc
        be=round(np.quantile(s,1-claim)/inc)*inc
        print(f"   {lbl:7s} {bn:11.2f} {100*(s>=bn).mean():6.2f}% | {bl:12.2f} {100*(s>=bl).mean():6.2f}% "
              f"| {be:14.2f} {100*(s>=be).mean():6.2f}%   (target {claim*100:.0f}%)")

print("="*84); print("FIX FOR RATIOS: lognormal, and simply using the player's own quantiles"); print("="*84)
compare("CS2 K/D", kd, 0.05)
compare("Dota 2 KDA", kda, 0.1)
compare("CS2 kills", cs2_kills.astype(float), 1.0)

print("\n"+"="*84); print("THE DENOMINATOR EXPLOIT applies to K/D too, not just headshot %"); print("="*84)
print("  A player whose TRUE skill is unchanged, but who plays fewer engagements per match:")
print(f"  {'engagements/match':>18} {'mean K/D':>9} {'sd K/D':>8} {'P(K/D >= 1.90)':>16}")
for lam in [0.85,0.5,0.3,0.15]:
    kk=rng.poisson(lam*R); dd2=rng.poisson(lam*R); r_=kk/np.maximum(dd2,1)
    print(f"  {lam*19.5:18.1f} {r_.mean():9.2f} {r_.std():8.2f} {100*(r_>=1.90).mean():15.1f}%")
print("  -> same true skill (kills rate == deaths rate), but a passive player clears a")
print("     'hard' K/D bar several times more often. Identical shape to the headshot exploit.")

print("\n"+"="*84); print("EFFECT OF A DENOMINATOR FLOOR on the headshot exploit"); print("="*84)
q=rng.beta(.42*60,(1-.42)*60,N)
hs=100*rng.binomial(np.maximum(cs2_kills,1),q)/np.maximum(cs2_kills,1)
for floor in [0,6,10,12,15]:
    m=cs2_kills>=floor
    sub=hs[m]; mu,sd=sub.mean(),sub.std(); bar=round(mu+K_H*sd)
    lo=(cs2_kills>=floor)&(cs2_kills<=8); hi=cs2_kills>=18
    a=100*(hs[lo]>=bar).mean() if lo.sum()>50 else float('nan')
    b=100*(hs[hi]>=bar).mean()
    print(f"  kill floor {floor:2d}: keeps {100*m.mean():5.1f}% of matches, hard bar={bar:3d}%  "
          f"low-kill clear={a:5.1f}%  high-kill clear={b:5.1f}%  gap={a/b if b>0 else 0:4.2f}x")
