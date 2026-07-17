# Business Model & Competitive Landscape

**Last updated:** 2026-07-15 (migrated from the PoC repo `clutchbook`; PoC code paths resolve under [`/poc-reference`](../../poc-reference/))
**Scope:** monetization audit under skill-gaming law, competitive positioning, retention mechanics across the no-money → gems → money arc. Gems legal structure lives in [`legal-compliance.md`](../legal/legal-compliance.md) §6; this doc covers the economy/retention design on top of it.

---

## 1. Monetization audit: the rake under skill-gaming law

### 1.1 Current mechanics (code-verified)

- Fixed, disclosed rake per objective: **8%** win-the-match, **12%** win-under-moves, 10% default (`api/_lib/skill_rating.rake_for`).
- Invariant `sum(payouts) + rake = sum(entries)` enforced on every settlement path and covered by the pytest suite.
- Rake is taken **only when a prize distributes**; refunds/cancellations rake nothing (solo pools with no clearers refund fully).

### 1.2 Legal assessment of the fee structure

This is the right structure. The legally load-bearing properties, all currently true:

1. **Fixed and disclosed, not outcome-priced.** A fee that varied with who wins would re-create a house position (vig). The per-objective differentiation (8% vs 12%) is fine — it prices *contest type*, not outcome.
2. **Neutral-operator revenue.** The platform never profits from a player losing — including the "no clearers → full refund, zero rake" solo branch, which is a genuinely strong fact pattern (many sweepstakes operators died on "the house wins when players fail").
3. **No rake on refunds** keeps the fee a service charge for a *completed* contest, not consideration retained regardless of service.

Rules to hold as the economy grows: no variable/surge rake tied to player skill or predicted outcome; no "insurance"/"cash-out early" products (those are house positions); promos/bonuses at money stage need counsel review (deposit-match bonuses pattern-match to gambling inducements in strict states).

### 1.3 Rake benchmarking

| Platform | Take |
| --- | --- |
| Players' Lounge | ~10% on H2H wagers |
| Skillz | effective 14–20%+ of entry fees (prize pools seeded below entries) |
| Poker rooms | 2.5–10% capped |
| DFS | ~10–15% of entry |
| **Money Match** | **8–12%** |

8–12% is competitive and defensible. At money stage, consider a lower headline rake on the hero H2H format (chess 8% → 6–7%) as a wedge against Players' Lounge, funded by higher-margin tournament formats. Secondary revenue (later, all wagering-clean): season passes/premium tournament formats (subscription via Stripe — legal because it's not a prize purchase), sponsored contests, B2B API for community tournaments.

---

## 2. Competitive landscape

### 2.1 The map

| Company | Model | Games | Verification | Status / lesson |
| --- | --- | --- | --- | --- |
| **Skillz** (NYSE: SKLZ) | In-house SDK games, P2P entry-fee tournaments, ~40 states | Casual mobile (solitaire, bowling…) | Full control (their SDK) | Proved the legal frame at scale; public-market struggles show UA costs eat thin rakes. Not a direct competitor (different games), but the legal template. |
| **Triumph (Triumph Labs)** | In-house arcade games, instant cash-out, iOS | Casual mobile | Full control | The UX bar for deposit→play→cash-out speed. Excludes more states than we plan to (their FAQ lists ~19). |
| **Players' Lounge** | **P2P wagers on games people already play** — our closest comp | Madden, NBA 2K, FIFA, CoD, Fortnite, Valorant… | **Self-report + screenshots + human dispute moderation** | Proves demand for the category (a16z-backed, years of operation). Weaknesses = our wedge: dispute hell, publisher-ToS gray zone on every title, console-first. |
| **CheckMate Gaming / UMG / GamerSaloon** | Same as Players' Lounge, older | CoD, Fortnite, 2K… | Self-report + disputes | Long-tail incumbents; high fraud/dispute friction; confirms the category and its ceiling without automation. |
| **1v1Me** | Pivoted from P2P wagers to **staking/spectator backing** of pros | CoD, NBA 2K… | Ops-run matches | Their pivot away from pure P2P wagering (liquidity is hard!) is the cautionary tale for our matchmaking-liquidity risk. |
| **Battlefy / Challengermode** | Tournament ops platforms — **no wagering** | Everything | Organizer-run | Not competitors; potential channel partners and the standard for community/organizer tooling. Battlefy monetizes organizers, not players. |
| **Boom Fantasy → Boom Entertainment** | Was esports/DFS props; pivoted to B2B games for sportsbooks/media (NBC Sports Predictor) | — | — | Lesson: consumer DFS-adjacent startups without a moat get consolidated; B2B pivot was their survival path. |
| **Chess.com / Lichess arenas** | Free or prize tournaments run by the platforms themselves | Chess | Native | If real-money chess wagering proves out, Chess.com could do it natively — speed and multi-game breadth are our defense. |

### 2.2 Positioning: where Money Match wins

**The one-line differentiation: API-verified, auto-settled P2P wagers — no screenshots, no disputes, no waiting.** Players' Lounge's model requires human moderators to adjudicate screenshot disputes; ours settles from host-API truth in under a minute. Second wedge: **skill-bracketed matchmaking** (nobody in the category does honest rating-band pairing; Players' Lounge is an open challenge board where sharks farm fish — bad retention for the fish). Third: **chess** — a huge, underserved, legally-cleanest vertical the CoD-wager incumbents ignore.

**Where we're weak:** liquidity (P2P needs concurrent players in the same game/format/stake/band — the cold-start problem that pushed 1v1Me to pivot); title breadth is constrained by our publisher-clean rule (Players' Lounge offers the gray-zone titles players actually ask for); no mobile app yet.

**Strategic implications:** (1) concentrate liquidity — one hero game (chess), few formats, few stake tiers, scheduled "power hours" rather than 24/7 thin queues; (2) sell the integrity story to players ("your winnings can't be dispute-stolen") and to investors (defensible in diligence where gray-zone comps aren't); (3) treat Battlefy-style community organizers as distribution, not competition.

---

## 3. Retention mechanics across the phases

### 3.1 What exists today (code-verified)

Leaderboard ranked by ROI (`leaderboard.py`), per-opponent H2H P&L history (Profile → My Contests), match spectating/tracking, multi-game filter. That's a decent skeleton and almost no *return trigger* — nothing brings a player back tomorrow.

### 3.2 No-money MVP (play money): prove the loop is fun without stakes

- **ELO-style platform rating per game** (distinct from host rating) — the number players grind. The `skill_rating.py` service is the natural home.
- **Streaks + daily challenge** ("win 1 H2H today"), light and cheap.
- **Friend challenges + rematch one-tap** (roadmap Phase 5) — the strongest organic loop; a challenge link is also an acquisition vector.
- **Notifications** (match found, settled, challenge received) — without these, a P2P platform can't maintain liquidity; players must be summonable.

### 3.3 Gems launch: gems are the retention engine, not revenue

Because gems are earned-only and non-cashable (legal design), their entire job is retention:

- **Earn:** daily login streak, first-win-of-day, contest completion, referral, season placement.
- **Sink:** entries to gem tournaments, cosmetics (profile flair, board themes, victory animations), leaderboard season passes.
- **Seasons:** monthly leaderboard resets with placement rewards — the proven ladder-retention loop; also generates the "season N champion" content beat for community.
- **Loss-recovery mechanics, carefully:** a "comeback bonus" of gems after a losing streak is fine at gem stage; at money stage it's an inducement — keep it gems-only forever.
- Target metrics: D1 > 40%, D7 > 20%, ≥3 contests/active week — see [`gtm-prelaunch.md`](./gtm-prelaunch.md).

### 3.4 Money launch: retention shifts from game-loops to trust-loops

- **Instant cash-out** (Triumph proved this is *the* retention feature in real-money skill gaming — payout latency is churn).
- Gems continue as the parallel status track (never convertible), so players who cash out still have season progress at stake — that's the reason to keep the gems ladder alive post-money.
- **Bankroll dashboard honesty** (ROI, P&L vs. rake paid) — counter-intuitive but the trust story is the brand; the segment that stays in real-money skill games is the segment that trusts the books.

---

## 4. Cold-start liquidity plan (the business risk that kills P2P platforms)

1. **Constrain the surface:** launch matchmaking with chess blitz at 2–3 stake tiers only. Every extra game/format/tier divides the queue.
2. **Scheduled liquidity:** nightly "arena hours" and weekend tournaments concentrate players into the same 2-hour window instead of trickling 24/7.
3. **Bots only as labeled play-money warmers** (existing roadmap rule) — never in gem-prize or money contests.
4. **Async formats absorb thin liquidity:** solo pools and leaderboard tournaments don't need a simultaneous opponent — lean on them while H2H liquidity builds (they're already built).
5. **Community-first GTM** (chess Discord/Twitch communities) rather than broad UA — see [`gtm-prelaunch.md`](./gtm-prelaunch.md).
