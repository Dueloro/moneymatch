# Legal & Compliance Analysis

**Last updated:** 2026-07-15 (migrated from the PoC repo `clutchbook`; PoC code paths resolve under [`/poc-reference`](../../poc-reference/))
**Status:** Research memo — working model for the team and a brief for gaming counsel. **Nothing here is legal advice**; every conclusion marked ⚖️ must be validated by specialist counsel before real money moves.

> Companion docs: [`integrity-audit.md`](./integrity-audit.md) (the product-side risks that create legal exposure), [`business-and-competition.md`](../business/business-and-competition.md) (rake/gems economics), [`roadmap.md`](../product/roadmap.md) (when each compliance workstream must land).

---

## 1. State-law posture: is the current model compliant in the ~37 skill-wagering states?

### 1.1 The short answer

**The structure is right; the state list is defensible; the current *demo* is compliant everywhere because it is play-money with no consideration.** The peer-to-peer, rake-only, no-house model described in [`overview.md`](../product/overview.md) §2 is the same legal frame Skillz (~40 states), Players' Lounge, and Triumph operate under today. Our client+server geo-fence excludes 14 states (`src/utils/states.ts`, `api/_lib/solo_challenge.py`), leaving 36 states + DC — the "37" in common parlance.

There is no single authoritative list of "37 legal states." Each operator's exclusion list reflects its counsel's risk tolerance:

| Operator | States excluded from cash play |
| --- | --- |
| **Players' Lounge** (closest comp) | 9: AR, CT, IN, LA, MT, SC, SD, TN, WY |
| **Money Match (current fence)** | 14: AZ, AR, CT, DE, FL, IN, LA, MD, MN, MT, SC, SD, TN, WY |
| **Triumph** (cash tournaments) | 12+: AZ, AR, CT, DE, FL, KY, LA, ME, MS, MT, SC, TN (FAQ lists a broader 19 incl. CO, MD, NE, NH, NM, WA) |

Our 14-state fence sits mid-pack conservative — a reasonable starting posture. ⚖️ Counsel must confirm the final list per contest type (H2H vs. pooled vs. solo) because states apply different tests:

- **Predominance / dominant-factor test** (majority of states): skill must predominate over chance. Chess is the strongest possible anchor.
- **Material-element test** (e.g., NY historically): gambling if chance is a *material* element even where skill predominates.
- **Any-chance test** (the strictest cohort — the core of our excluded list): any chance element can taint the contest; in SC, courts have signaled that where a *wager* exists, skill is irrelevant.

### 1.2 Per-game skill analysis (this is where the current roadmap has a real weakness)

The skill-predominance argument is **per game**, not per platform:

| Game | Skill-predominance strength | Notes |
| --- | --- | --- |
| Chess | Excellent | Near-pure skill; deterministic; deep rating system. The hero title for a reason. |
| CS2 | Good, with caveats | Human execution dominates, but round economy, spawn/teammate variance in non-1v1 modes introduce chance arguments. 1v1/2v2 arranged matches are cleaner than queue matches with 8 strangers. |
| Dota 2 | Moderate | Literal RNG mechanics in-game (crit chance, item drops) + 9 strangers determine outcomes in pub matches. **Wagering on the outcome of a solo-queued pub match is the weakest skill story we currently offer** — 80% of the result is players who aren't party to the contract. Restrict to arranged 1v1-mid or team-vs-team formats. |
| Clash Royale (planned) | Moderate | Card-draw randomness; the solo-pool "elixir efficiency" metrics framing helps but doesn't cure it. Also a publisher-ToS dead end (§2). |
| Rocket League (planned) | Excellent mechanically | No RNG — but Epic-owned, publisher-ToS dead end (§2). |

**Recommendation:** for real money, launch chess-only; add CS2/Dota only in *arranged head-to-head formats* (the Phase 1 brokered/coordinated model already points this way) and get a per-title counsel opinion before enabling each.

### 1.3 Climate warning

The regulatory climate has turned hostile toward *anything* that pattern-matches to unlicensed gambling: the 2025–26 sweepstakes-casino crackdown (§6) and the June 2026 PA Supreme Court ruling that physical "skill games" are gambling devices are different verticals, but they show AGs are actively hunting. The defense is discipline: never house-banked, never chance-resolved, rake always disclosed, geo-fence enforced with real geolocation (not a dropdown).

---

## 2. Game publisher ToS compliance

### 2.1 Verdict table

**This is the single biggest unresolved legal/business risk in the roadmap.** The platform's data layer and its right to exist per title depend on publisher tolerance.

| Publisher / platform | Wagering posture | Verdict for Money Match |
| --- | --- | --- |
| **Lichess** (chess) | API is open for personal *and* commercial use; no explicit anti-wagering clause found. But Lichess is a **charity** whose mission is free chess. | 🟡 **Usable now; talk to them before scale.** They ask commercial integrators to contact them (lichess.org/contact). A real-money layer on a charity's free infrastructure is a reputational/relationship risk even if technically permitted. Have the conversation before gems launch; budget for a Chess.com-API fallback adapter. |
| **FaceIt** (CS2) | Developer ToS could not be publicly retrieved (403); FaceIt itself runs paid-entry competitions, historically the most commercially open esports platform. | 🟡 **Conditional.** Read the developer terms from inside the dev portal; pursue a written commercial/partner agreement before any money (even gems with prizes) settles off FaceIt data. FaceIt has a partner program — this is a business-development task, not just legal. |
| **Valve** (CS2, Dota via Steam data) | Steam Web API ToS + Subscriber Agreement prohibit gambling businesses; Valve has issued C&Ds to betting sites since 2016 and bans gambling use of its OpenID/API. | 🔴 **Do not build on Steam Web API directly.** Our Dota adapter uses OpenDota (community mirror of Valve's public match data) — one step removed but the underlying data rights are Valve's, and OpenDota's own terms don't grant wagering rights they don't have. The compliant commercial path is a **licensed aggregator (GRID — Valve's official data partner — or PandaScore)** whose enterprise tier explicitly covers real-money use (see `docs/old/Esports Data Infrastructure.md`; ~$2–5k/mo at that tier). |
| **Riot** (LoL, Valorant, TFT) | Developer policy is explicit: *"Your product cannot feature betting or gambling functionality."* | 🔴 **Off the table.** Do not target Riot titles. |
| **Epic** (Fortnite, **Rocket League**) | Community rules + event license terms prohibit wagering; Epic actively bans wager-match participants. | 🔴 **Off the table — including Rocket League**, which the app currently shows as "coming soon" and features in solo-pool metric examples. Remove it from the roadmap and UI. |
| **Activision** (CoD, Warzone) | No public API; brand terms prohibit gambling association. Wager platforms (Players' Lounge, CMG) operate in this gray zone via self-report/screenshots. | 🔴 **Avoid.** No API means no host-authoritative settlement anyway — it would force us into the self-report model we reject in [`integrity-audit.md`](./integrity-audit.md). |
| **Supercell** (Clash Royale) | Tournament guidelines: all events must be **free to enter**, no gambling/paid raffles/fantasy betting. | 🔴 **Off the table for money; remove "coming soon."** Free-entry gem contests *might* fit their free-tournament rules — ⚖️ verify before even the gems phase uses CR. |

### 2.2 Which games *should* we target?

Selection criteria: (a) open or licensable API with match-level results, (b) publisher that tolerates or licenses wagering-adjacent use, (c) strong skill-predominance, (d) existing ranked ladder for bracketing.

1. **Chess — Lichess (now) + Chess.com Published-Data API (fallback/expansion).** Keep as hero.
2. **CS2 + Dota 2 via GRID/PandaScore licensed feeds** at the money stage; OpenDota/FaceIt free tiers are fine for the no-money demo, per their sandbox norms.
3. **Trackmania / speedrun-style time-trial games** — deterministic, timing-based, easy pooled contests; check Ubisoft API terms.
4. **StarCraft II** (Blizzard API exists; check terms — same corporate family as Activision, likely restrictive).
5. **Golf/pool/darts simulators with open APIs** — the Skillz category proven in court, worth scanning.
6. **Age of Empires, chess-adjacent turn-based ladders (e.g., Go via OGS)** — OGS has an open API and a Lichess-like ethos.

The strategic point: **breadth of titles is not the moat — verified auto-settlement is.** Only add titles whose data layer we can defend in a diligence room.

---

## 3. Age verification

### 3.1 Now (play-money demo / no-money MVP)

- No statutory age-verification duty for free play, but keep the **18+ self-attestation** (already on `Landing.tsx`) because the product is wagering-adjacent and app-store/ad policies treat it as such.
- **COPPA:** we must not knowingly collect personal data from under-13s. Once we add accounts/emails (waitlist, gems), add a neutral age gate (birthdate entry, not a checkbox) at signup.
- Watch state minor-design laws (age-appropriate design codes in several states) once we have real accounts.

### 3.2 Gems phase (no cash, but prizes/leaderboards)

- If gems are purely earned and non-cashable (see §6), an 18+ attestation + birthdate gate suffices. If gem contests award any tangible prize, treat as §3.3.

### 3.3 Real money

- **Verified DOB via KYC document/database check — attestation no longer suffices.** Industry standard: verify at account funding or first withdrawal, and before that at signup via DOB + identity-data check.
- Minimum ages vary: **18 baseline; 19 in AL and NE; 21 in AZ, IA, LA, MA** (per DFS-style precedent — PrizePicks/DFS regs). ⚠️ **Massachusetts — our declared launch state — is a 21+ state under its DFS regulations (940 CMR 34).** ⚖️ Confirm whether skill contests inherit the 21+ DFS floor in MA; the age gate must be per-state configurable, not a global 18.
- Geolocation must be a real check (GeoComply/Radar-class GPS verification), not the current self-selected dropdown.

---

## 4. Payment processor compatibility

### 4.1 The blunt facts

- **Stripe: prohibited.** Stripe's restricted-business list explicitly names *"games of skill … with a monetary or material prize,"* including video-game tournaments. Real-money entries/payouts on Stripe = account termination and frozen funds. (Stripe remains fine for anything non-wagering: SaaS-style subscriptions, merch.)
- **PayPal/Venmo: restricted.** Gambling/skill-gaming merchants need explicit pre-approval and licensure evidence; unapproved wagering activity gets accounts frozen. Venmo *as a payout rail via a gaming-approved processor* is how Triumph does "instant cash-out" — that's the processor's program, not a raw PayPal merchant account.
- Card networks distinguish MCC 7994 (games/arcades) from MCC 7995 (gambling); acquirers decide where a skill operator lands, and it materially affects approval, chargeback treatment, and issuer decline rates.

### 4.2 The real path (proven by comps)

| Layer | Vendors to evaluate | Notes |
| --- | --- | --- |
| Acquiring / gateway | **Nuvei, Worldpay (gaming vertical), Checkout.com** | The gaming-vertical processors; expect underwriting: counsel opinion letter, geo-fence proof, RG program, reserve requirements. |
| A2A / ACH deposits & instant withdrawals | **Aeropay** (Skillz's partner), Trustly, Plaid+Dwolla | A2A is the skill-gaming workhorse — cheaper than cards, lower chargeback exposure, real-time payouts via RTP. |
| Payout orchestration | PayNearMe, Dots, Astra | Venmo/debit-push/ACH payout menus. |
| Cash/alt deposits | PayNearMe | Optional, later. |

**Practical sequencing:** underwriting takes 2–4 months and requires the legal opinion letter, so the payments workstream starts *during* the gems phase, not after it. Until then, never attach Stripe to anything that touches contest entries — including gem *purchases* if gems can win prizes (processors treat that as sweepstakes-adjacent; §6 recommends not selling gems at all).

---

## 5. KYC / AML once real money enters

### 5.1 Regulatory hooks

- **UIGEA** does not prohibit skill contests where bettors are participants — but it puts the burden on *payments* companies, which is exactly why processors underwrite us so hard.
- **FinCEN / BSA:** holding player wallets, escrowing entries, and paying out winnings can make the platform a **Money Services Business (money transmitter)** — FinCEN reads hybrid wallet products expansively. Options, in ascending cost: (a) ⚖️ counsel opinion that the escrow-agent/payment-processor exemption applies; (b) FinCEN MSB registration + AML program (cheap federally; the pain is (c)); (c) **state money-transmitter licenses** — 40+ states, seven figures and years. The standard startup answer is **structure custody through a licensed partner** (sponsor bank / licensed transmitter / the payments partner's FBO account) so we never hold funds in our own name. This decision shapes the wallet architecture in [`roadmap.md`](../product/roadmap.md) Stage C and must be made before a line of production payments code is written.

### 5.2 Program requirements (regardless of MSB outcome — processors will demand these)

- **KYC:** identity + DOB + address verification (Persona/Socure/Idenfy-class vendor) at the earlier of: cumulative deposits ≥ threshold (our planned $500 is in line; Skillz KYCs at first withdrawal), or first withdrawal. Document step-up for high risk.
- **Sanctions/OFAC screening** at KYC and on an ongoing basis.
- **AML monitoring:** velocity rules on deposit/entry/withdrawal; same-instrument-in/out default; flag deposit→minimal-play→withdraw patterns (classic laundering through P2P wagers — and note our anti-collusion analytics double as AML detection, see `integrity-audit.md` §5).
- **SAR capability** on the audit ledger (roadmap Phase 2 ledger is the substrate).
- **Tax:** collect W-9 and issue **1099-MISC at $600+ net winnings/year**; per-state withholding rules ⚖️.
- **Responsible gaming:** the demo's loss cap is currently cosmetic (`useWallet.canJoin` bug — see `poc-reference/POC-IMPLEMENTATION.md` §14.1); it must be genuinely enforced, with self-exclusion, cool-downs, and limits raisable only after delay. Processors and states audit this.

---

## 6. Structuring the gems economy so it isn't a "virtual currency" gambling problem

### 6.1 The cautionary tale

2025–26 was the era of the **sweepstakes-casino crackdown**: the dual-currency model (buy Gold Coins, get "free" Sweeps Coins, redeem for cash) was banned by statute in CA (AB 831), NY, MT, CT, NJ, NV, IN, ME, IA, OK, MS and counting, with AG enforcement against operators *and vendors*. The lesson: **a virtual currency becomes a gambling instrument when purchased value can round-trip to real-world value through a chance- or wager-shaped mechanic.**

The three gambling elements are consideration, chance, and prize. Our contests already attack *chance* (skill). The gems design must also cleanly break **consideration→prize round-tripping**:

| Design | Consideration | Prize | Verdict |
| --- | --- | --- | --- |
| Gems **earned only** (play, streaks, referrals), **never sold, never cashable**, spent on cosmetics/entries to gem contests | None | No redeemable value | ✅ Safe — this is a loyalty/XP system |
| Gems sold for $, not cashable (closed loop) | Yes | None (if truly no prizes) | 🟡 Legal as entertainment, but gem *wagers* with sold gems start looking like value-at-risk; processors get nervous |
| Gems sold for $ **and** winnable gems redeemable for cash/prizes | Yes | Yes | 🔴 The banned sweepstakes model. Never. |

### 6.2 Committed design rules for the gems launch

1. **Gems are never sold for money.** Earned via play, daily streaks, referrals, seasonal placement. (Also keeps Stripe usable for any future non-wagering revenue.)
2. **Gems are never redeemable** for cash, gift cards, or tangible prizes, and are **non-transferable between users** (P2P transfer = de facto cash-out market; this also kills a collusion-laundering vector).
3. Gems buy **status and access**: cosmetics, leaderboard seasons, entry into gem-pot contests whose winnings are… more gems.
4. **Hard wall between gems and the future cash wallet** — separate ledger, separate currency type, no exchange path in either direction, ever. Cash launch adds a cash wallet beside gems; it does not convert them.
5. Keep the rake mechanic in gem contests (it tunes the economy and rehearses the real-money math) but understand it has no legal significance while gems are valueless.
6. Marketing discipline: never describe gems as "money," "cash," "winnings you can cash out later," and never promise conversion at real-money launch — a promised future exchange rate creates present value.

⚖️ Have counsel review the final gem T&Cs against the new sweepstakes statutes (several are drafted broadly enough to warrant a check even for a no-purchase design).

---

## 7. Priority actions

1. **Now:** remove Rocket League / Clash Royale "coming soon" surfaces; stop implying Riot/Epic/Supercell titles are on the roadmap.
2. **Now:** adopt the gems design rules (§6.2) before any gems code is written.
3. **Gems phase:** open conversations — Lichess (blessing), FaceIt (partner/commercial terms), GRID/PandaScore (licensed CS2/Dota data quotes).
4. **Gems phase:** engage gaming counsel (fixed-scope: state survey for chess H2H + pooled contests, MSB analysis, opinion letter for processors, gem T&Cs).
5. **Pre-money:** payments underwriting (Nuvei/Worldpay + Aeropay), KYC vendor, geolocation vendor; per-state age matrix incl. MA 21+ question.
