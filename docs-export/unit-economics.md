# Illustrative Unit Economics

**Last updated:** 2026-08-10.
**Scope:** a bottom-up, assumption-driven model of per-payer and per-DAU economics for the pitch deck — the economic *framework* Dueloro plans to validate in beta, not historical operating results. The live rake structure and its legal footing live in [`business-and-competition.md`](./business-and-competition.md) §1; the metrics program that will replace these assumptions with measured data lives in [`gtm-prelaunch.md`](./gtm-prelaunch.md).

> **Naming.** This is investor / pitch-deck material, so it speaks at the *company* level and uses **Dueloro** throughout — consistent with the marketing-site voice. Inside the product the same activity is branded **Money Match** (see [`../brand-and-name.md`](../brand-and-name.md) §1). "Dueloro attachment", "Dueloro session", etc. below mean "a gaming session in which the player runs the Money Match overlay".

> **Rake note — OPEN DECISION (read before quoting numbers).** This model assumes a **15% platform rake** (14.55% effective after ties/refunds). The current product default is **10%** (`services/money_math.py::DEFAULT_RAKE_BPS = 1000`), and [`business-and-competition.md`](./business-and-competition.md) §1.3 benchmarks a live band of **8–12%**.
>
> **We have not decided whether to launch at 10% or 15%** — this is deliberately unresolved. The 15% here is a *modeling input for the deck's upside framing*, not a committed rake. Every revenue and contribution figure below scales roughly linearly with the rake, so at 10% the effective rake is ~9.7% (`10% × 0.97`) and per-payer revenue drops by about a third (PUBG ~$24.70/mo instead of $37.10; CS2 ~$14.80 instead of $22.26). Keep the two straight when presenting, and revisit this once beta gives us a read on price sensitivity and competitive positioning vs. Players' Lounge (~10% on H2H).

---

## Disclaimer (put this on the section's opening slide)

Dueloro is pre-scale, so engagement, retention, customer-acquisition cost, wallet velocity and transaction-cost assumptions remain **unvalidated**. The following model is management's current best estimate and is intended to show the economic framework we plan to validate during beta — not a claim about results we have already achieved.

Every number carries one of three labels, used consistently throughout:

- **EXTERNAL BENCHMARK** — supported by outside data (cited).
- **MANAGEMENT ASSUMPTION** — a current Dueloro estimate, not yet measured.
- **BETA KPI** — a number Dueloro will measure directly after launch.

---

## Slide 1 — The economic model

**Dueloro monetizes gaming activity that already exists.**

Core formula:

```
Revenue = Paying Players
        × Gaming Frequency
        × Dueloro Attachment
        × Contests per Session
        × Average Entry
        × Effective Rake
```

Shared assumptions (MANAGEMENT ASSUMPTION unless noted):

| Input | Value | Note |
| --- | --- | --- |
| Entry tiers | $5 / $10 / $25 | |
| Estimated entry mix | 60% / 30% / 10% | |
| Weighted average entry | **$8.50** | `5·0.60 + 10·0.30 + 25·0.10` |
| Platform rake | 15% | see rake note above |
| Estimated tie / refund rate | 3% | no rake taken on refunds |
| **Effective realized rake** | **14.55%** | `15% × (1 − 3%)` |

Contest modes: 3-player solo pools, 10-player tournaments, friend-to-friend head-to-head. The Dueloro overlay lets a player enter a paid contest **without leaving the underlying game**.

**Design note (the loop to show visually):**

```
Existing gaming session → Dueloro overlay → Paid contest → Match → Result → Re-entry opportunity
```

---

## Slide 2 — PUBG behavioral model

**PUBG creates several contest opportunities within a normal gaming session.**

> **EXTERNAL BENCHMARK.** A full PUBG round can last roughly 30 minutes, while players eliminated earlier can immediately start another match. *(WIRED.)*

Management assumptions and the derived chain:

| Step | Value | Derivation |
| --- | --- | --- |
| PUBG gaming time | 25 hrs/month | MANAGEMENT ASSUMPTION |
| Average session length | 2 hrs | MANAGEMENT ASSUMPTION |
| Gaming sessions/month | 12.5 | `25 ÷ 2` |
| Dueloro session attachment | 60% | MANAGEMENT ASSUMPTION |
| Dueloro-active sessions/month | 7.5 | `12.5 × 60%` |
| Paid contests per attached session | 4 | MANAGEMENT ASSUMPTION |
| Paid contests/month | 30 | `7.5 × 4` |
| Average entry | $8.50 | shared assumption |

**Economics per retained PUBG payer:**

- Monthly handle: `30 × $8.50 = $255`
- Monthly Dueloro revenue: `$255 × 14.55% = $37.10`

**Variable-cost planning model** (per retained PUBG payer, per month):

| Cost line | Basis | Amount |
| --- | --- | --- |
| Payment processing | ~4.1% of deposits; deposits assumed at 30% of handle (`$76.50`) | ~$3.14 |
| Chargeback / fraud reserve | 1% of deposits | ~$0.77 |
| Payout cost reserve | 0.3% of handle | ~$0.77 |
| API / cloud | $0.01 per contest × 30 | ~$0.30 |
| KYC amortization | ~$1.39 per verification, amortized | small |
| Variable support / fraud allowance | — | small |
| **Total estimated variable cost** | | **~$5.69** |

- **Estimated monthly contribution: ~$31.41** (`$37.10 − $5.69`)
- **Illustrative contribution margin: ~85%** — *label preliminary.*

> **EXTERNAL BENCHMARK / caveat.** Generic card pricing (e.g. Stripe's current 2.9% + $0.30) is useful only as a modeling benchmark; paid games of skill are restricted and may require specialized processing and approval. *(Stripe.)* Current Veriff Plus self-serve pricing is approximately $1.39 per verification. *(Veriff.)*

---

## Slide 3 — PUBG scale economics

**PUBG economics at different paying-DAU levels.**

Per-payer figures reduce to a clean **per paying-DAU/day** unit (a retained payer is active 7.5 days/month and runs 4 contests/active day):

- Handle/day: **$34.00** (`4 × $8.50`)
- Revenue/day: **$4.95** (`$34.00 × 14.55%`)
- Contribution/day: **$4.19** (`$31.41 ÷ 7.5`)

| Paying DAU | Handle/day | Revenue/day | Contribution/day | Revenue/month | Contribution/month |
| --- | --- | --- | --- | --- | --- |
| 1 | $34.00 | $4.95 | $4.19 | $148.50 | $125.70 |
| **1,000** | **$34,000** | **$4,950** | **$4,190** | **$148,500** | **$125,700** |
| **5,000** | **$170,000** | **$24,750** | **$20,950** | **$742,500** | **$628,500** |

*(Display the 1,000 and 5,000 rows prominently.)*

---

## Slide 4 — CS2 behavioral model

**CS2 offers fewer contests per session than PUBG, but potentially strong repeat competitive behavior.**

> **EXTERNAL BENCHMARK.** Standard CS2 Competitive / Premier matches generally run roughly 30–45 minutes under the current MR12 structure. Shorter modes (Casual, Wingman) create contest-frequency upside if supported. *(Winio.)*

| Step | Value | Derivation |
| --- | --- | --- |
| CS2 gaming time | 20 hrs/month | MANAGEMENT ASSUMPTION — *not a claimed published CS2 average; keep this explicit in the deck.* |
| Average session length | 2 hrs | MANAGEMENT ASSUMPTION |
| Gaming sessions/month | 10 | `20 ÷ 2` |
| Dueloro attachment | 60% | MANAGEMENT ASSUMPTION |
| Dueloro-active sessions/month | 6 | `10 × 60%` |
| Contests per attached session | 3 | MANAGEMENT ASSUMPTION |
| Paid contests/month | 18 | `6 × 3` |
| Average entry | $8.50 | shared assumption |

**Economics per retained CS2 payer:**

- Monthly handle: `18 × $8.50 = $153`
- Monthly Dueloro revenue: `$153 × 14.55% = $22.26`
- Estimated variable costs: ~$3.56/month
- **Estimated contribution: ~$18.70/month**
- **Illustrative contribution margin: ~84%** — *label preliminary.*

---

## Slide 5 — CS2 scale economics

**CS2 economics at different paying-DAU levels.**

Per paying CS2 DAU (active 6 days/month, 3 contests/active day):

- Handle/day: **$25.50** (`3 × $8.50`)
- Revenue/day: **$3.71** (`$25.50 × 14.55%`)
- Contribution/day: **$3.12** (`$18.70 ÷ 6`)

| Paying DAU | Handle/day | Revenue/day | Contribution/day | Revenue/month | Contribution/month |
| --- | --- | --- | --- | --- | --- |
| 1 | $25.50 | $3.71 | $3.12 | $111.30 | $93.60 |
| **1,000** | **$25,500** | **$3,710** | **$3,120** | **$111,300** | **$93,600** |
| **5,000** | **$127,500** | **$18,550** | **$15,600** | **$556,500** | **$468,000** |

---

## Slide 6 — PUBG vs. CS2

**Each supported game has a different economic profile.**

| Metric | PUBG | CS2 |
| --- | --- | --- |
| Gaming hours/month | 25 | 20 |
| Sessions/month | 12.5 | 10 |
| Dueloro-active sessions/month | 7.5 | 6 |
| Contests per attached session | 4 | 3 |
| Paid contests/month | 30 | 18 |
| Monthly handle / payer | $255 | $153 |
| Monthly revenue / payer | $37.10 | $22.26 |
| Monthly contribution / payer | $31.41 | $18.70 |
| Contribution margin | ~85% | ~84% |
| Active days/month | 7.5 | 6 |
| DAU equivalent per retained payer | 0.25 | 0.20 |
| Handle / paying DAU / day | $34.00 | $25.50 |
| Revenue / paying DAU / day | $4.95 | $3.71 |
| Contribution / paying DAU / day | $4.19 | $3.12 |

**Key message:** the economics do not depend on every game behaving identically. Dueloro evaluates each game independently on player frequency, match cadence, attachment rate and average wager behavior.

---

## Slide 7 — Acquisition model

**The launch strategy combines paid acquisition with creator-driven distribution.**

| Scenario | Blended CAC | Monthly payer retention |
| --- | --- | --- |
| Paid-only downside | $50.00 | 30% |
| **Steve base case** | **$16.67** | **45%** |
| Viral upside | $5.00 | 55% |

> **Definition — CAC.** Total acquisition spend ÷ first-time *paying* users. Not cost per impression, signup, or download. Creators, referrals and earned media reduce blended CAC even where paid-media CAC remains materially higher.

---

## Slide 8 — What does it cost to build DAU?

Using the **Steve base case** (45% retention, $16.67 blended CAC):

A retained payer's active days convert to sustained DAU, then retention discounts first-time payers to sustained DAU:

| Game | Active days/mo | DAU per retained payer | × 45% retention | Sustained DAU per first-time payer |
| --- | --- | --- | --- | --- |
| PUBG | 7.5 | 0.25 (`7.5 ÷ 30`) | | **0.1125** |
| CS2 | 6 | 0.20 (`6 ÷ 30`) | | **0.09** |

**Approximate acquisition requirements** (first-time payers = target DAU ÷ sustained-DAU factor; spend = payers × $16.67):

| Target DAU | Game | First-time payers needed | Acquisition spend |
| --- | --- | --- | --- |
| 1,000 | PUBG | ~8,889 | ~$148K |
| 5,000 | PUBG | ~44,444 | ~$741K |
| 1,000 | CS2 | ~11,111 | ~$185K |
| 5,000 | CS2 | ~55,556 | ~$926K |

> **Investor takeaway.** Our earlier ~$360K estimate for 5,000 DAU assumed much higher monthly engagement. Under this more conservative session-based model, **~$740K–$930K** of cumulative acquisition spend is a more defensible base-case range if all DAU came from a single game (the low end is all-PUBG, the high end all-CS2). This is exactly why the model must stay **dynamic**.

---

## Slide 9 — Multi-game portfolio case

**Dueloro does not need 5,000 DAU from one game.**

Illustrative portfolio: **2,500 PUBG DAU + 2,500 CS2 DAU = 5,000 total paying DAU.**

| | PUBG (2,500 DAU) | CS2 (2,500 DAU) | Total |
| --- | --- | --- | --- |
| First-time payers needed (base case) | ~22,222 | ~27,778 | **~50,000** |
| Cumulative acquisition spend @ $16.67 | | | **~$834K** |
| Monthly contribution | ~$314K | ~$234K | **~$548K** |

The ~$548K is **monthly contribution before fixed overhead and future acquisition spend**. All figures illustrative.

---

## Slide 10 — Why the model can improve

**Several variables can materially improve unit economics.** Five levers:

1. **Higher attachment.** 60% → 70% turns more existing gaming sessions into Dueloro sessions.
2. **More contests per session.** PUBG 4 → 5 contests raises handle/player by 25%.
3. **Higher average entry.** The current weighted average is only $8.50 despite a $25 top tier.
4. **Higher retention.** 45% → 55% monthly payer retention lowers the acquisition spend required to sustain a fixed DAU target by ~18% (`1 − 45/55`).
5. **Organic acquisition.** Creator-driven distribution and player referrals cut blended CAC.

---

## Slide 11 — What beta must validate

**The beta converts these assumptions into measured unit economics.** Track by game and cohort (all BETA KPI):

1. First-time payer CAC
2. Monthly payer retention
3. D1 / D7 / D30 payer retention
4. Underlying game hours/month
5. Gaming sessions/month
6. Dueloro session attachment rate
7. Contests per attached session
8. Average entry value
9. Entry-tier distribution
10. Handle per retained payer
11. Handle per paying DAU
12. Wallet velocity
13. Deposit-to-handle ratio
14. Tie / refund rate
15. Chargeback rate
16. KYC cost
17. Payment-processing cost
18. Withdrawal cost
19. API / cloud cost per contest
20. Contribution per payer
21. Contribution per paying DAU
22. Contribution LTV / CAC
23. Pool fill rate
24. Median time to fill
25. Re-entry rate after completed contests

Every dashboard result should be filterable by: **game · contest mode · entry tier · acquisition channel · creator/referral code · new vs. retained payer · cohort month.**

---

## Implementation workflow for developers

The instrumentation that feeds slide 11 already exists in part — money/liquidity events flow to PostHog (see [`gtm-prelaunch.md`](./gtm-prelaunch.md) §1.1). The model itself should be built the same way: one source of truth, everything else computed.

### Step 1 — Store all assumptions centrally

Do not hard-code numbers into slide designs. Create a single economics config object/table:

```
rake_rate, tie_rate, average_entry, entry_mix,
gaming_hours_monthly_pubg, gaming_hours_monthly_cs2, session_hours,
attachment_rate, contests_session_pubg, contests_session_cs2,
retention_downside, retention_base, retention_upside,
cac_downside, cac_base, cac_upside,
deposit_handle_ratio, processing_rate, chargeback_reserve,
payout_rate, kyc_cost, api_cost_contest, variable_support_cost
```

All charts and slide values calculate from this source. (This mirrors how the product already keeps rake config-driven in basis points rather than sprinkled through the code.)

### Step 2 — Use formulas, not manual numbers

For every game:

```
Gaming Sessions / Month  = Gaming Hours ÷ Session Length
Dueloro Sessions         = Gaming Sessions × Attachment Rate
Monthly Contests         = Dueloro Sessions × Contests per Session
Monthly Handle / Payer   = Monthly Contests × Average Entry
Platform Revenue / Payer = Monthly Handle × Rake × (1 − Tie Rate)
DAU Conversion           = Monthly Retention × (Dueloro Active Days ÷ 30)
First-Time Payers Needed = Target DAU ÷ DAU Conversion
Acquisition Spend        = First-Time Payers Needed × CAC
```

### Step 3 — Build sensitivity controls

The developer model should allow instant adjustment of, with player revenue, contribution, DAU economics, acquisition spend and break-even DAU all recomputing live:

| Lever | Range |
| --- | --- |
| Rake | 10% / 12.5% / 15% / 17% |
| Attachment | 30–80% |
| Contests/session | 2–6 |
| Average entry | $5–$15 |
| Retention | 20–70% |
| CAC | $5–$100 |
| Tie rate | 0–10% |

### Step 4 — Visually distinguish facts from assumptions

Use the three labels throughout — **EXTERNAL BENCHMARK**, **MANAGEMENT ASSUMPTION**, **BETA KPI** — as defined in the disclaimer. This is important for investor credibility.

### Step 5 — Keep the deck focused

The main presentation should show ~6–8 economics slides; detailed assumptions and sensitivity tables go in an appendix. Recommended main-deck order:

1. Economic engine
2. PUBG case
3. CS2 case
4. Comparison
5. Acquisition strategy
6. DAU scaling
7. Base / downside / upside
8. Beta validation plan

Everything else belongs in appendix slides.

---

## Final investor message

> These are deliberately soft numbers. Dueloro does not yet have enough operating history to claim precise retention, CAC or play-frequency figures. What we have built instead is a transparent bottom-up model driven by gaming frequency, match cadence, contest attachment, average entry and a platform take. Under the current conservative base case, PUBG generates ~$37 of monthly platform revenue per retained payer and CS2 ~$22. The beta is designed to replace each management assumption with measured cohort data. The point is that we already know which variables determine the economics and exactly what we need to measure to validate them.
