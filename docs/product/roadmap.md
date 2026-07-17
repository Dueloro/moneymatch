# Money Match — Full Product Roadmap (demo → no-money MVP → gems launch → real money)

**Last updated:** 2026-07-15 (migrated from the PoC repo `clutchbook`)

> **Migration note.** **Stage A (the no-money MVP) is now being executed in this
> repo via the [implementation guide](../implementation-guide/00-README.md)** —
> the guide supersedes A1–A4 for engineering detail (it extends Stage A with
> the design-PDF frontend, admin tools, demo payment rails, and payments/KYC
> readiness). Stages B and C remain the forward plan after the MVP ships.
> PoC code paths (`api/…`, `src/…`) resolve under [`/poc-reference`](../../poc-reference/).

This is the master plan from today's play-money demo to a real-money launch, in
three stages. It is both a product and a technical roadmap: every milestone has
engineering deltas and exit criteria. It supersedes the previous phase-only
roadmap (Phases 0–5 are mapped into the stages below).

Supporting analysis (read once, reference often):
[`legal-compliance.md`](../legal/legal-compliance.md) ·
[`integrity-audit.md`](../legal/integrity-audit.md) ·
[`business-and-competition.md`](../business/business-and-competition.md) ·
[`gtm-prelaunch.md`](../business/gtm-prelaunch.md) ·
[`IMPLEMENTATION.md`](../../poc-reference/POC-IMPLEMENTATION.md) (code ground truth) ·
[`overview.md`](./overview.md) (product definition)

**The invariant model never changes:** peer-to-peer / pooled, rake-only, no
house. `sum(payouts) + rake = sum(entries)` on every settlement, at every stage.

---

## The three stages at a glance

| | **Stage A — No-money MVP** | **Stage B — Gems launch** | **Stage C — Real-money launch** |
| --- | --- | --- | --- |
| Money | Play money | **Gems: earned-only, never sold, never cashable, non-transferable** | Real cash + gems as parallel status track |
| Audience | Private beta (waitlist invites) | Public | Public, geo-fenced states, per-state age gate |
| Games | Chess (hero) + CS2/Dota arranged H2H | Same; publisher conversations decide additions | Chess first; CS2/Dota only on licensed data + counsel sign-off |
| Legal posture | Nothing to comply with (no consideration) | Gem T&Cs reviewed; counsel engaged; publisher terms secured | Opinion letter, KYC/AML program, payments underwriting, RG program |
| Core engineering theme | **Server-authoritative everything** | Economy, retention, integrity v1, ops | Payments, compliance rails, integrity v2, hardening |
| Exit test | Tampered client can't change a cent; two strangers complete a real match end-to-end | D7 > 20%, ≥3 contests/wk core, zero integrity incidents in a season | First 100 real-money contests settle with 0 disputes, 0 invariant breaks, clean audit |

Timeboxes are indicative for a 2–3 person team: **A ≈ 8–10 wks · B ≈ 10–12 wks
(+ counsel/partner lead time running in parallel) · C ≈ 12–16 wks** (gated on
external partners more than code).

---

# Stage A — No-money MVP (private beta)

**One sentence:** the demo becomes a real multi-user product — server-owned
state, real accounts, verified identities, and provable play-money — with the
demo's self-report seams removed.

**What already exists (mapped from old Phases 0–1.5):** the full play-money
loop against real game data (three adapters), server-side matchmaking queue
with brokered Lichess challenges (old Phase 1, done), recommendation dots +
settlement modal (old Phase 1.5, done). What's demo-shaped: localStorage
state, client-trusted money math, self-reported solo/tournament telemetry, no
auth. See `IMPLEMENTATION.md` §13–14.

### A1 — Server-authoritative state (the big rewrite; old Phase 2, expanded)

The single architectural rule that fixes integrity vulns #1–#3
(`integrity-audit.md`): **the server owns every number.**

- **Postgres** (Neon/Supabase — fits the Vercel deploy): `users`,
  `linked_accounts`, `wallets`, `contracts`, `solo_pools`, `tournaments`,
  `matches`, `ledger_events`.
- **Append-only ledger:** every wallet mutation (escrow, settle, rake, refund,
  limit change) is an immutable event; balances are derived. This is the audit
  substrate for Stage C's AML/SAR duties — build it right once.
- **Settle-by-id:** `POST /api/contracts/settle` (and solo/tournament settle)
  take only an id; entry/pot/rake/`matched_at`/`account_id` come from the DB.
  Client-posted `Contract` objects and client telemetry are removed from the
  API surface.
- **Server-fetched telemetry:** the server pulls solo/tournament telemetry
  from host APIs itself (the CS2 path already exists server-side —
  `CS2FaceitAdapter.norm_to_telemetry`; route it server-to-server). **Delete
  the "I cleared it / I missed" buttons and `genTelemetry`/`genScore`.** Games
  without server-fetchable telemetry don't get solo pools — period.
- **Background settlement worker** (cron/queue) replaces the client 15s poll;
  the client just subscribes to state (poll or SSE).
- Matchmaking queue state moves from in-memory (`match_queue.py`) to
  Postgres/Redis so restarts can't strand escrowed entries.
- Fix the loss-limit tautology in `useWallet.canJoin` — enforcement moves
  server-side with the wallet anyway.

*Exit criteria:* balances identical across two devices; any settled contest
reconstructs event-by-event from the ledger; a hand-crafted malicious settle
request cannot alter any amount; invariant reconciliation view reads straight
from the ledger.

### A2 — Real identity: auth + OAuth account binding

- **Platform auth** (Clerk/Supabase Auth/Lucia): email or OAuth sign-in,
  sessions, one wallet per user. Kills client-chosen `player_id`.
- **Lichess OAuth linking** as the default chess bind (scoped read + challenge
  permission); username-claim demoted to a read-only preview. FaceIt OAuth2 /
  Steam OpenID for CS2/Dota binds.
- **Immutable bindings:** one host account binds to one platform user;
  rebinding requires support action (schema: unique constraint + audit event).
- **Targeted challenges:** brokered chess matches become direct challenges
  between the two bound Lichess accounts (not open-challenge URLs), and
  settlement verifies the game's players are exactly the two bound accounts —
  closes the ringer seam (`integrity-audit.md` §3).

*Exit criteria:* two strangers on separate machines sign up, link via OAuth,
queue, play a brokered game that only their accounts could occupy, and settle
— with zero manual steps.

### A3 — Instrumentation + waitlist (runs in parallel, days not weeks)

Per `gtm-prelaunch.md`: point `track()` at PostHog + server-side event log;
activation-funnel and liquidity dashboards; waitlist capture (email + game +
state) on Landing; Discord stood up; weekly metrics snapshot begins.

### A4 — Cleanup that protects the story

- Delete or quarantine the legacy Electron overlay (house-edge odds contradict
  the no-house model).
- Remove Rocket League / Clash Royale "coming soon" surfaces (publisher-ToS
  dead ends — `legal-compliance.md` §2).
- README with real run instructions.

---

# Stage B — Gems launch (public)

**One sentence:** open the doors with a gems economy that drives retention and
growth while staying legally inert — and build the integrity and operator
muscles the money stage requires.

### B1 — Gems economy (design rules from `legal-compliance.md` §6.2 are law)

- New `currency` dimension on wallets/ledger: `GEMS` beside `PLAY` — same
  escrow/rake/invariant machinery, separate books, **no exchange path** (and
  none to the future cash wallet, ever).
- **Earn:** signup grant, daily streak, first-win-of-day, settled-contest
  completion, referral qualification, season placement.
- **Sink:** gem-entry contests (all three formats already generalize),
  cosmetics (profile flair, board/card themes), season pass.
- **Non-transferable** between users (also caps collusion laundering).
- Gem T&Cs drafted and counsel-reviewed against the 2025–26 sweepstakes
  statutes before launch.

### B2 — Retention & liquidity loops (old Phase 5, re-scoped; see `business-and-competition.md` §3–4)

- Platform ELO per game + monthly **seasons** with placement rewards.
- **Friend challenges + one-tap rematch** — deep links double as acquisition.
- **Notifications** (match found, settled, challenge received): in-app + push
  + email — the liquidity summoning system.
- **Scheduled arenas** ("power hours", weekend tournaments) to concentrate
  thin liquidity; Discord announcement bot.
- Referral program: two-sided gem reward on referee's first *settled* contest;
  waitlist position-referral converts to launch invites.

### B3 — Integrity v1 (old Phase 4, now mandatory pre-public; `integrity-audit.md` §4–5)

- Host-account floors for rated queues: min account age, min rated games,
  non-provisional rating (per-adapter thresholds).
- Stateful `can_pair`: pair-frequency cooldowns from server-side pair history.
- Device fingerprint + IP clustering; block intra-cluster pairing.
- Directional value-flow flagging between account pairs (gems now, AML later).
- Host cheat-flag ingestion (Lichess marks) + ledgered clawback.
- Cap matchmaking band widening for gem-prize contests.

### B4 — Operator surface (old Phase 3)

- Ops dashboard: queue depth, time-to-match, settlement latency, DAU/funnel,
  gem GGV/rake, per-game liquidity, **risk view** (flags, freezes, pair
  blocks) — actions work without a deploy (per-game/per-user kill switches).

### B5 — External workstreams (start of Stage B; these gate Stage C)

- **Gaming counsel engaged** (fixed scope: state survey for chess H2H + pooled,
  MSB/money-transmitter analysis, opinion letter, gem T&Cs, promo rules).
- **Publisher/data conversations:** Lichess blessing; FaceIt commercial/partner
  terms; GRID/PandaScore enterprise quotes for CS2/Dota (decision input: keep
  or cut those titles at money stage).
- Payments pre-underwriting conversations (Nuvei/Worldpay + Aeropay) — 2–4
  month lead time.

*Stage B exit:* public, D7 > 20%, core plays ≥3 contests/week, a season
completes with zero unhandled integrity incidents, counsel opinion in hand,
data rights secured for every title that will carry money.

---

# Stage C — Real-money launch

**One sentence:** cash enters through licensed partners, in permitted states,
with KYC/AML, real geolocation, and enforced responsible gaming — chess first.

### C1 — Compliance rails (gates everything)

- **Corporate:** Delaware C-Corp (per `docs/old/Corporate Structure.md`),
  IP assignment, cap table — investors and processors both require it.
- **State matrix v1 from counsel:** launch states (MA posture confirmed —
  including the 21+ DFS-age question), final excluded list per contest type;
  geo-fence list becomes config, not code constants.
- **Geolocation partner** (GeoComply/Radar-class GPS verification) replaces the
  residence dropdown for cash play; dropdown remains only for free play.
- **KYC vendor** (Persona/Socure-class): DOB/identity/address verification at
  funding threshold or first withdrawal; OFAC screening; per-state age matrix
  (18/19/21).
- **MSB decision executed** per counsel: custody structured through the
  licensed partner (FBO account) so the platform never holds funds in its own
  name — this dictates wallet architecture, so it's decided before C2 code.

### C2 — Payments & cash wallet

- Deposits: A2A/ACH via Aeropay-class partner + cards via gaming acquirer
  (Nuvei/Worldpay). Withdrawals: instant via RTP/debit-push (Triumph-parity
  payout speed is a retention feature, not a nicety).
- Cash wallet as a third currency on the existing ledger (`CASH` beside
  `GEMS`/`PLAY`) — same invariant machinery, now with deposit/withdrawal event
  types, same-instrument-in/out default, velocity rules.
- Phase-1 caps from `overview.md` §7.3 ($1–$100 entries, $200 daily loss, $500
  KYC threshold, $20 min withdrawal, 3 concurrent contests) as **server-enforced
  config**.
- Tax: W-9 collection + 1099-MISC at $600 net winnings/year.

### C3 — Responsible gaming (real this time)

- Deposit/loss/session limits enforced server-side; lowerable instantly,
  raisable after 24h cooldown; self-exclusion 7-day→permanent; reality-check
  prompts; rake always displayed pre-join. Processors and states audit this.

### C4 — Integrity v2

- Payment-instrument clustering joins device/IP clustering; AML velocity
  monitoring + SAR workflow on the ledger; collusion flags escalate to holds
  with human review; post-settlement clawback path tested end-to-end;
  security hardening + external pen test.

### C5 — Controlled rollout

1. **Chess-only, 2–3 launch states, invite-only cash cohort** from the best
   gem-season players; low caps.
2. Watch: dispute rate (target 0 by construction), invariant reconciliation,
   payout latency, fraud flags, state mix.
3. Widen states → raise caps → add CS2/Dota **only if** licensed data + per-title
   counsel opinion landed in B5/C1.

*Stage C exit = the real launch:* 100 consecutive real-money contests with
zero disputes, zero invariant breaks, KYC/geo pass rates healthy, and a
regulator-ready audit trail for any of them on demand.

---

## Cross-cutting tracks (live in every stage)

- **Legal:** every new contest type, metric, promo, and state change gets
  checked against the frame (skill predominates; neutral operator; no
  consideration→prize round-trip). `legal-compliance.md` is the reference.
- **Integrity:** the audit table in `integrity-audit.md` §1 is the backlog;
  its per-stage exit tests are release gates.
- **Data/publisher relations:** no title carries prizes without secured data
  rights. Adapters keep the seam cheap; the GameAdapter interface is the
  hedge against any single host souring.
- **Metrics:** the four investor narratives (`gtm-prelaunch.md` §1.2) are
  standing dashboards from Stage A onward.

## Product principles (unchanged)

- **Depth over breadth** — chess is the hero; add titles only when the core
  loop is excellent *and* the data rights are clean.
- **Bots are play-money-only queue warmers**, always labeled.
- **Trust is the brand:** rake disclosed, invariant visible, every movement
  auditable, settlements host-verified — the moat over every screenshot-and-
  dispute competitor.
