# GTM & Pre-Launch Infrastructure

**Last updated:** 2026-07-15 (migrated from the PoC repo `clutchbook`. PoC code paths resolve under [`/poc-reference`](../../poc-reference/). The analytics items in §1 are implemented by [implementation-guide Phase 6](../implementation-guide/09-phase-6-admin-ops.md); the invite-link mechanics in §3.2 by [Phase 5](../implementation-guide/08-phase-5-social-retention.md).)
**Scope:** what to measure now for the investor story, the waitlist/community gaps in the current codebase, and referral mechanics. Retention design lives in [`business-and-competition.md`](./business-and-competition.md) §3.

---

## 1. Metrics to capture now (even in the demo)

### 1.1 Current state (code-verified)

The seam exists and is empty: `src/utils/telemetry.ts` defines 12 stable event names (`entry_queued`, `match_found`, `contest_settled`, `rake_collected`, …) but `track()` only `console.debug`s in dev. `@vercel/analytics` gives anonymous page views only. **Nothing user-level is captured — every demo session's story evaporates.**

### 1.2 The investor-story metrics, by narrative

Investors in this category ask four questions; each maps to metrics we can start capturing in the demo *this week* by pointing `track()` at a real sink (PostHog or Amplitude — both have free tiers, PostHog recommended for self-serve funnels + session replay):

**"Do people get it?" — activation funnel.** `landing_viewed → gate_passed → account_linked → first_contest_joined → first_settlement`. Report each conversion %. The linked-account step is our unique friction and *the* number to obsess over.

**"Is there a there there?" — engagement depth.** Contests per active user per week; % of users with ≥2 games linked; D1/D7/D30 retention; session frequency. Benchmarks to beat: D1 40%, D7 20%, ≥3 contests/week for the core.

**"Can it make money?" — simulated economics.** Play-money GGV (gross entries), rake accrued, average stake, contests per liquidity hour. Even fake-dollar numbers demonstrate the *mechanics* of unit economics; pair with the invariant reconciliation (Phase 2 ledger) as the "our books are provable" slide.

**"Does the marketplace clear?" — liquidity health.** Time-to-match distribution per (game, format, tier); queue abandonment rate; % matches settled vs. expired/refunded; settlement latency. These come from the server (`match_queue.py` events), not the client — instrument both.

**Integrity metrics as a differentiator:** % settlements host-verified (target 100%), dispute count (target 0 by construction), collusion flags. No competitor can show this slide.

### 1.3 Implementation notes

- Add server-side event logging alongside the client `track()` — client-only analytics undercount and can't see the queue.
- Log the anonymized funnel *even for the gate-bounce* (state selected, blocked state attempts = market-demand data for excluded states).
- Start a weekly one-page metrics snapshot now; a 6-month metric *history* at seed time is worth more than a good week.

---

## 2. Waitlist & community infrastructure — current gaps

**The codebase has zero acquisition or contact infrastructure.** Verified gaps:

| Gap | Evidence | Fix |
| --- | --- | --- |
| No email capture anywhere | `Landing.tsx` collects age-check + state only | Waitlist form on Landing (email + which game you play + handle), stored server-side (this is the first real DB table — fine to ship before full auth) |
| No accounts | mock `started` flag in localStorage | Real auth is a no-money-MVP item (see roadmap); waitlist email becomes the seed identity |
| No social presence links | no Discord/X links in the app | Add Discord as the community home — the standard for both chess and esports audiences; footer + post-settlement prompts |
| No shareable artifacts | settlement modal (Phase 1.5) renders only in-app | "Share result" card: image/link of the win (game, stake, opponent rating, payout) — every win becomes an ad |
| No SEO/landing surface | SPA with a brand wall | A real marketing page (what/why/waitlist) separate from the app shell |
| Blocked-state users bounce silently | gate disables Start | Capture their email too ("we'll tell you when free-play launches in your state") — free-play is legal everywhere and they're future money users if laws change |

**Community sequencing:** Discord first (cheap, high-signal beta cohort + the liquidity coordination channel — "arena hour starts in 10 min" pings solve cold-start), then embedded waitlist referral ranking, then creator partnerships (chess Twitch/YouTube is dense with mid-size creators who take sponsorships; a "creator arena" with a gem prize pool is the natural first activation).

---

## 3. Referral & invite mechanics

### 3.1 Pre-launch (waitlist phase)

**Position-based waitlist referral** (the proven Robinhood/Superhuman loop): each signup gets a referral link; referrals move you up the queue; top-N get founding-member perks (badge, gem grant at launch, early arena access). Cheap to build (one table + one counter) and it makes the waitlist itself the growth channel.

### 3.2 In-product (gems phase)

- **Two-sided gem reward:** referrer + referee each get gems when the referee completes a *qualifying action* — first **settled contest**, not signup (settlement is fraud-resistant since it requires a real linked account and a real played game; signup-triggered rewards get farmed).
- **Challenge-a-friend deep link** (roadmap Phase 5 friend challenges) is the organic loop: a challenge link sent to a non-user is an invite with a built-in first action. Prioritize it as *acquisition*, not just engagement.
- **Referral leaderboard + season credit** for community champions.
- Anti-abuse from day one: device fingerprint + linked-account uniqueness on referee reward (ties into the integrity clustering work — see [`integrity-audit.md`](../legal/integrity-audit.md) §4); gems non-transferability caps the damage of any farm.

### 3.3 At money launch

Cash referral bonuses are standard in the category but are **marketing inducements with compliance surface** (state-by-state promo rules; bonus abuse = AML flag). Keep referral rewards in gems even post-money until counsel clears a cash program.

---

## 4. Pre-launch checklist (ordered)

1. Point `track()` at PostHog + add server-side event log (days, not weeks).
2. Ship waitlist capture (email + game + state) on Landing + a marketing page.
3. Stand up Discord; wire "join Discord" into post-settlement and empty-queue states.
4. Add waitlist referral ranking.
5. Weekly metrics snapshot doc; define the four investor-narrative dashboards (§1.2).
6. Shareable win cards when the Phase 1.5 settlement modal ships.
