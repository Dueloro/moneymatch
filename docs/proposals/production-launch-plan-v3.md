> **Status: domain design adopted; stack not adopted (2026-07-15).** Migrated
> from the PoC repo. This plan's wagering-product designs are incorporated into
> the [implementation guide](../implementation-guide/00-README.md): per-metric
> player models + frozen baseline snapshots, personal-bar solo-pool rooms with
> averaged room bars (§4.5b–c), duel-forecast H2H pairing (§4.5d–e), matchmade
> stat tournaments (§4.6), the failure-mode matrix (§6.2), the ledger chart of
> accounts + solvency invariant (§3.1), restricted Lichess challenges and the
> Dota expose-data link check (§6.1).
>
> **Not adopted:** the Firebase/Firestore/Vercel-cron stack (this repo uses
> Postgres + FastAPI + a settlement worker — see guide `00-README.md` §2; same
> server-authoritative principles, different substrate), Stripe test-mode
> integration in the MVP (payments stay behind the `PaymentProvider` seam;
> Stripe-vs-gaming-PSP is a Phase-B decision), and the Electron overlay
> (backlogged). **Note:** the `api/_lib/demo/` module this plan cites
> (`demo/ledger.py`, `demo/matcher.py`) was never committed to the PoC repo —
> those components are specified here and built fresh in the MVP.

# Money Match — Production Launch Plan (v3)

**Last updated:** 2026-07-12
**Scope of this revision:** reworks **solo pools into queue-matched rooms with an averaged pass bar** (§4.5b–c) and **tournaments into matchmade single-metric rooms with top-3 payouts** (§4.6). v2 added the **Stripe-backed central money system**, the **stat-banded matchmaking + friends system**, and a **feasibility/reliability review** of every wagering product. Supersedes v1/v2 of this document.

**Goal:** a publicly usable web platform with real users backed by **Firestore**, an internal **double-entry ledger** as the bank with **Stripe as the money on/off ramp**, skill-banded matchmaking so players only see (and get matched into) contests against similar-stat opponents or friends, and a downloadable **in-game overlay** showing the current wager for the game being played. Three games at launch: **Chess (Lichess), CS2 (FaceIt), Dota 2 (OpenDota)**. Modern Warfare deferred (fails the adapter gate: no stable public per-player match API).

**Companion docs:** [`IMPLEMENTATION.md`](../../poc-reference/POC-IMPLEMENTATION.md) (code-verified current state), [`overview.md`](../product/overview.md) (product/legal model), [`roadmap.md`](../product/roadmap.md) (long-range phases).

---

## 0. Phasing — the honest frame

Two hard constraints shape everything:

1. **Real-money skill wagering is a *restricted* business on Stripe.** Gambling is prohibited outright; real-money skill contests / fantasy-style products require **Stripe's prior written approval** before you may process a single live dollar. Approval takes weeks and is not guaranteed. Processing real-money entries on an unapproved account gets the account frozen with funds held — an existential event for a wagering platform.
2. **Real money also requires the compliance stack** (KYC, geofencing via a real geolocation signal, counsel sign-off per state, tax reporting) from roadmap §2. None of it compresses into two weeks.

So the plan is two phases, built on **one architecture**:

- **Phase A (weeks 1–2, this sprint): public play-money launch.** Real users, real matchmaking, real friends, real settlement against real game results, the overlay — with the ledger, wallet, and Stripe integration built **production-shaped and running in Stripe test mode** behind a kill-switch flag. Every money code path that Phase B needs is exercised in Phase A with virtual currency.
- **Phase B (weeks 3–6, gated): flip real money on.** Stripe live keys + approved account + KYC + counsel. Because Phase A built the rails, Phase B is approvals + configuration + hardening, not architecture.

Submit the Stripe platform application **on day 1 of Phase A** (with the peer-to-peer skill-contest legal memo from `overview.md` §2/§9) so the approval clock runs concurrently with the build.

---

## 1. Where we are (recap)

Verified in `IMPLEMENTATION.md`: the game adapters (Lichess/FaceIt/OpenDota) and the invariant-tested settlement engines are real and good. Everything else money-shaped is demo-grade: no accounts (mock gate), all opponents are bots, wallet/contracts live in `localStorage` (client-editable), settlement is a client poll loop, and the Electron overlay renders a legacy odds card pointed at `clutchbook.app`. The new `api/_lib/demo/` module contributes two seams this plan promotes to production: the **double-entry integer-cents ledger** (`demo/ledger.py` — balanced postings, conservation asserts) and the **`SkillMatcher` interface** (`demo/matcher.py` — z-scored skill vectors, exact distance now, ANN later). The demo's manual-outcome endpoints must be gated out of production.

---

## 2. Target architecture

```
                 ┌─────────────────┐        ┌──────────────────────────┐
                 │ Firebase Auth    │        │ Stripe                    │
                 │ (Google + email) │        │  Checkout (deposits)      │
                 └───────┬─────────┘        │  Connect Express (payouts │
                         │ ID token          │   + KYC)  · Radar · 1099  │
                         ▼                   └───────┬─────────▲────────┘
┌──────────────┐   ┌──────────────────────────┐     │webhooks │transfers
│ React web app │──►│ FastAPI on Vercel         │◄────┘         │
│ (Vercel CDN)  │   │  · verifies ID token      │───────────────┘
└──────┬────────┘   │  · ALL money writes       │
       │ onSnapshot │  · PaymentProvider seam   │        ┌───────────────────┐
       │ (reads)    │  · SkillMatcher seam      │◄──────►│ Host game APIs     │
       │            └──────────┬───────────────┘  cached │ Lichess/FaceIt/    │
       │                       │ firebase-admin          │ OpenDota           │
       │            ┌──────────▼───────────────┐         └───────────────────┘
       └───────────►│ Firestore                 │
                    │  users · links · friends  │   Crons (Vercel):
┌──────────────┐    │  wallets · ledger         │    · settle-sweep   (1/min)
│ Electron      │──►│  contracts · lobby        │    · match-widen    (1/min)
│ overlay       │   │  soloPools · tournaments  │    · watchdog       (5/min)
│ (read-only)   │   │  queues · inbox · flags   │    · reconcile      (daily)
└──────────────┘    └──────────────────────────┘
```

Principles (each one closes a current hole):

- **The internal ledger is the bank; Stripe is only the on/off ramp.** Wagers, escrow, rake, refunds — thousands of movements — happen as balanced ledger postings inside Firestore transactions. Stripe sees exactly two event types: a deposit in, a withdrawal out. This is the poker-room/Skillz pattern: it keeps per-wager latency off the card networks, keeps Stripe's risk team looking at a simple "wallet top-up" flow, and makes the wager engine provider-agnostic.
- **Clients never write money.** Firestore rules deny client writes to every money-bearing collection; the Admin SDK (server) is the only writer. Clients send *intent*; the server computes every amount.
- **Every mutation of value goes through one `post_ledger()` helper** (promoted from `demo/ledger.py`): balanced legs in integer cents, conservation asserted, appended immutably. Wallet documents are a *derived cache* of the ledger, updated in the same transaction.
- **Settlement, matching, and hygiene are server crons**, idempotent and transaction-guarded. No correctness ever depends on a client tab being open.
- **Two swap seams stay abstract:** `PaymentProvider` (Stripe today; a gaming PSP like Nuvei/Paysafe/Aeropay if Stripe declines the real-money application) and `SkillMatcher` (exact distance today; pgvector/ANN when populations grow).

### 2.1 Firestore data model

All amounts **integer cents**. Collections (client access noted):

```
users/{uid}                    profile, residence, 18+ attestation, friendCode,
                               limits, riskFlags            [owner r/w non-money fields]
users/{uid}/links/{game}       linked host account, verifiedAt, immutable   [owner r]
users/{uid}/friends/{fuid}     edge: status, since                          [owner r]
users/{uid}/inbox/{id}         notifications: match found, challenge, settle [owner r]
friendRequests/{id}            from, to, status                             [parties r]
wallets/{uid}                  { availableCents, escrowCents, version }     [owner r]
ledger/{id}                    balanced posting: txType, legs[], refs, ts   [owner r own legs]
stripeEvents/{eventId}         processed-webhook dedupe marker              [server only]
payouts/{id}                   withdrawal requests: state machine           [owner r]
contracts/{id}                 H2H: uids[], game, state, entry, pot, rakePct,
                               objective, matchedAt, windowEnds, accountIds [parties r]
lobby/{id}                     OPEN contest cards: game, band, visibility,
                               creatorUid, invitedUids[], entry, expiresAt  [authed r, see §4]
queues/{game}/tickets/{id}     matchmaking ticket: product ∈ duel|pool|tourney,
                               metric, difficulty?, tier, personalBar?,
                               band, tolerance, since                       [owner r]
soloPools/{id} (+entries/)     matchmade room: roomBar, memberBars{uid},
                               difficulty, metric, band, state              [parties r; friends-posted: friends r]
tournaments/{id} (+entries/)   matchmade room: metric, prizeTable, window,
                               scores{uid}, band, state                     [parties r]
skill/{uid}/{game}             skillScore, band, vector[], sampleSize, at   [owner r]
config/flags                   kill switches, bands, tiers, rakes           [authed r]
```

Rules: `allow write: if false` on wallets, ledger, contracts, lobby, queues, pools, tournaments, payouts, skill, friends edges (server writes all of them); reads scoped as noted. Rules covered by emulator tests in CI.

---

## 3. The money system: internal ledger + Stripe

### 3.1 Ledger accounts (chart of accounts)

```
user:{uid}:available     spendable balance
user:{uid}:escrow        entries locked in OPEN/MATCHED/ACTIVE contests
user:{uid}:receivable    negative-balance tracking after a chargeback (Phase B)
platform:rake            accumulated rake revenue
platform:promo           promotional credits funding (so promos never mint value silently)
stripe:clearing          money in transit to/from Stripe (Phase B)
stripe:fees              Stripe's processing fees (Phase B)
```

Every posting's legs sum to zero (the demo ledger already asserts this). Two audit invariants run as a nightly cron and must hold **always**:

1. **Conservation per contest:** `sum(payouts) + rake == sum(entries)` for every settled contract/pool/tournament (already unit-tested; now also audited against the live ledger).
2. **Solvency:** `sum(user available + escrow) == deposits − withdrawals + promo − rake` (Phase A: `== promo funding − rake` since all money is minted by promo). Drift → page immediately, flip the global joins kill switch.

### 3.2 Money flows

**Deposit (Phase B; test mode in Phase A).**
1. Client → `POST /api/wallet/deposit` `{ amountTier }` (fixed tiers, e.g. $10/$25/$50/$100 — no free-form amounts).
2. Server creates a Stripe **Checkout Session** (hosted page — card data never touches us; PCI scope stays SAQ-A) with `metadata.uid`, and a `payment_intent` idempotency key derived from `(uid, clientRequestId)`.
3. Stripe webhook `payment_intent.succeeded` → verify signature → **transaction:** create `stripeEvents/{event.id}` (fails if it exists → duplicate, no-op) + post ledger `deposit` (`stripe:clearing → user:{uid}:available`, fee leg to `stripe:fees`) + update wallet doc.
4. Client sees the balance move via `onSnapshot`. **Never** credit on the client redirect URL — only on the webhook.

**Entry / escrow.** `POST /api/contracts` or `/join`: one Firestore transaction validates wallet ≥ entry, checks limits (§7), posts `hold` (`available → escrow`), writes/updates the contract. The transaction retries on contention; the wallet doc carries a `version` for optimistic-lock sanity.

**Settlement.** The settle-sweep cron grades via the adapter, then one transaction: re-read contract state (no-op unless `ACTIVE|RESOLVING` — makes double-fire safe), post `settle` legs (`escrow → winner:available`, `escrow → platform:rake`), flip state, write inbox notifications. Refund paths post `refund` (`escrow → available`, zero rake).

**Withdrawal (Phase B).**
1. User completes **Stripe Connect Express onboarding** once (Stripe collects SSN/ID — **this is our KYC**, run by Stripe, including sanctions screening; we store only the account id and verification status).
2. `POST /api/wallet/withdraw` → transaction: validate (min $20, verified Connect account, no risk flags, funds outside any hold window), post `withdrawal_pending` (`available → stripe:clearing`), create `payouts/{id}` in `PENDING`.
3. Server creates a Stripe **Transfer** to the connected account (idempotency key = payout id), then a payout to their bank/debit. Webhooks drive `payouts/{id}` → `PAID` or → `FAILED` (which reverses the ledger posting).
4. Stripe generates **1099s** for connected accounts above IRS thresholds — tax reporting handled.

**Chargeback (`charge.dispute.created`, Phase B).** Freeze the wallet (risk flag blocks joins + withdrawals), post the disputed amount `available → user:{uid}:receivable` (may drive available negative — that's the point), submit evidence (deposit receipt, contest ledger, ToS acceptance). The fraud pattern to expect is *deposit → lose intentionally to an accomplice → charge back*; the §7 anti-collusion controls and a **48–72h withdrawal hold on freshly deposited funds** are the mitigations.

### 3.3 Provider abstraction

```python
class PaymentProvider(ABC):
    def create_deposit_session(uid, amount_cents, request_id) -> CheckoutRef: ...
    def handle_webhook(payload, signature) -> list[MoneyEvent]: ...   # verified, normalized
    def onboard_payee(uid) -> OnboardingRef: ...                      # KYC + payout rails
    def send_payout(uid, amount_cents, payout_id) -> PayoutRef: ...   # idempotent

class StripeProvider(PaymentProvider): ...      # Phase A: test mode behind flags
class NullProvider(PaymentProvider): ...        # Phase A production: deposits disabled
```

Settlement and the wallet never import Stripe. If Stripe declines the restricted-business application, we implement the same interface on a gaming-specialized PSP (Nuvei, Paysafe, Aeropay, Trustly — all serve licensed skill-gaming operators) without touching the wager engine. This seam is cheap now and priceless later.

### 3.4 Reconciliation (the fool-proofing layer)

A daily cron pulls Stripe's balance transactions and asserts, per currency: `sum(ledger stripe:clearing legs) == Stripe net balance movement`, and re-runs the two §3.1 invariants over the full ledger. Any mismatch: alert + flip `flags.depositsEnabled=false`. Money bugs must fail *closed* and *loudly*. In Phase A this runs against test-mode data — the audit machinery gets weeks of burn-in before a real dollar exists.

---

## 4. Matchmaking: skill-banded discovery + quick match

Design goals, in tension and resolved in this order: **(1) fair** — you only ever face similar-stat opponents; **(2) fast** — a player with intent should be in a contest in seconds, not minutes; **(3) legible** — the player always sees *why* this match is fair.

### 4.1 The skill layer

Per `(uid, game)` we maintain a `skill/{uid}/{game}` doc, computed at link time and refreshed on every settlement (and daily):

- **`skillScore`** — a single scalar in host-native units: chess = Lichess rating for the relevant time control; CS2 = FaceIt Elo; Dota = MMR estimate (rank-tier midpoint when MMR is hidden).
- **`band`** — a discrete integer 0–7 from **fixed, published boundaries** per game (e.g. chess: <900, 900–1150, 1150–1400, 1400–1650, 1650–1900, 1900–2150, 2150–2400, >2400; CS2 on Elo; Dota on MMR). Fixed boundaries (not rolling percentiles) keep Firestore queries stable and the system explainable — "Band 4: 1650–1900" is legible to players.
- **`vector`** — the z-scored multi-stat vector from `demo/matcher.py` (CS2: K/D, ADR, HS%, KPR, win rate, Elo; analogous per game). The **band gates discovery**; the **vector ranks candidates and powers the match-quality label** ("Even match", "Reach"). Behind the existing `SkillMatcher` interface; upgrade to pgvector ANN is a later swap, not a redesign.
- **`sampleSize`** — host games played. Below a floor (20 rated games chess / 30 matches CS2 / 30 exposed matches Dota) the account is **provisional**: it can play friendlies and bot practice but cannot post or join open rake-bearing contests. This is the anti-smurf/anti-sandbag floor: the band comes only from host-verified history, never self-report, and a settlement-time re-check refuses to settle if the linked account's identity changed.

### 4.2 Discovery: who sees what

Every `lobby/{id}`, `soloPools/{id}`, `tournaments/{id}` doc denormalizes `band` (creator's band) and `visibility ∈ public | friends | direct`. A viewer with band `b` sees:

```
visible(doc, viewer) =
     (doc.visibility == public  AND doc.band ∈ {b−1, b, b+1})
  OR (doc.visibility == friends AND doc.creatorUid ∈ viewer.friends)
  OR (doc.visibility == direct  AND viewer.uid ∈ doc.invitedUids)
  OR  doc.creatorUid == viewer.uid
```

Firestore implementation: the public feed is one indexed query — `where game == g AND state == OPEN AND visibility == public AND band in [b−1, b, b+1] orderBy createdAt desc` (composite index committed in `firestore.indexes.json`; `in` supports up to 30 values so ±1 is trivial and a later widening to ±2 still fits). Friends' contests come from a second query, `where creatorUid in [chunked friend uids]` (§5.3). The two result sets merge client-side; server endpoints enforce the same predicate on **join** (never trust the feed filter alone — the join endpoint re-checks band/friendship/invite so a hand-crafted request can't jump bands).

**Public solo pools and tournaments are no longer browse-and-join surfaces** — they are queue-matched rooms (§4.5b–c, §4.6), so the feed shows *your own* in-flight rooms plus friends-posted pools, not a directory of strangers' pools. The banded predicate above still gates the two card types that remain posted: lobby H2H contests and friends/direct pools (a pool posted by a Band-3 player is visible to Band 2–4 friends). Band ±tolerance also remains the coarse pre-filter inside every matchmaking queue.

### 4.3 Quick match: the seamless path

Posting-and-waiting is the fallback; the primary flow is **one tap → matched**:

1. `POST /api/queue/{game}` `{ entryTier, format, metric }` — the server escrows the entry and, **inside the same transaction**, scans `queues/{game}/tickets` for a compatible ticket: same format + entry tier + wagered metric, band within the ticket's current tolerance, duel fairness per §4.5(d), passes `can_pair` (§7). Match found → both tickets deleted, contract created `MATCHED`, inbox notifications + (chess) the Lichess challenge link written. **Match-on-write means two compatible players pair in a single round trip** — no polling latency at all.
2. No candidate → the ticket persists with `tolerance = 0` (own band only).
3. The **match-widen cron** (1/min) relaxes waiting tickets: ±0 bands for the first 30s, ±1 to 2min, ±2 after — and re-attempts pairing on each pass. The client shows the honest state the roadmap already specifies: current band range being searched + live queue depth.
4. Give-up path: after N minutes, offer (a) keep waiting, (b) convert to a posted lobby contest (visible to bands ±1 per §4.2), (c) cancel → instant refund. A ticket TTL (watchdog, §6.4) guarantees no entry stays escrowed in a dead queue.
5. **Practice fill:** if the queue is empty, offer a clearly-labeled `BOT` practice contest instantly (zero rake, refund-on-settle, excluded from leaderboards). Nobody ever hits a dead end; real liquidity is never faked.

Match-quality on the confirmation card comes from the vector distance (`ExactMatcher` over the candidate set), so even inside a band the *closest* waiting opponent is chosen and the fairness is displayed, not asserted.

### 4.4 Cold-start liquidity

Banded visibility fragments early liquidity (that's its cost). Mitigations: launch to one community at a time (a single Discord fills two bands, not eight); widen tolerance faster when queue depth is low (the widen cron reads depth); friends bypass bands entirely (§5); bot practice keeps the app alive at depth zero. Do **not** widen public visibility beyond ±2 — fair matching is the product.

### 4.5 The pairing algorithm in full: stat duels + baseline-derived pools

Product decision this section implements: **nobody — player or platform — ever sets odds, a line, or a payout number.** Every threshold in the system is a deterministic, disclosed function of host-verified stats. Solo pools are *clear-the-bar* rooms: each player queues at a difficulty (Easy / Medium / Hard) whose bar is quoted from **their own baseline**, the matcher groups similar-stat players into a room, and the room's single pass bar is the **average of the matched players' personal bars** — so no entrant inherits a bar built from someone else's stats. H2H (for CS2/Dota) is a **stat duel** — both players wager equal stakes on one chosen metric, and whoever posts the higher value in their next qualifying match wins. Chess H2H stays win-the-game (two players in the *same* game is the purest duel and needs no stat model). Matchmaking is what makes every product fair, and it operates at two levels: the **band** (coarse, powers feed visibility, §4.2) and the **per-metric model** below (fine, powers room composition and pairing).

**(a) The per-metric player model.** For every `(uid, game, metric)` we maintain, from the player's last **N = 20** finished matches with recency weighting (exponential, half-life 10 matches):

```
metricModel = { mu, sigma, n, updatedAt }     # EWMA mean + std dev of per-match values
```

- **Metrics are rate-based only** — K/D, ADR, HS%, KPR, win rate (CS2); KDA, GPM (Dota). Never raw totals (total kills rewards long matches) and never anything outside the player's control (round count, map). The typed `MetricKind` union is the allowlist, which is also the no-prop-bet guarantee (overview §10.3).
- **`n < 10` → the metric is provisional** for that player: no stat duels or pool entries on it (bot practice only). You cannot be matched on a metric we cannot model.
- The model refreshes on every settlement and nightly. The values a live contest uses are **frozen at escrow time** (a `baselineSnapshot` stored on the contract/entry), so a baseline cannot be manipulated between join and play, and any dispute can replay the exact inputs that produced the bar or the pairing.

**(b) Solo pools — queue first; every player's bar is quoted from their own baseline.** The player picks game + metric + **difficulty ∈ {Easy, Medium, Hard}** + entry tier and enqueues (`POST /api/queue/pool/{game}`). At enqueue time the server escrows the entry, freezes the player's `baselineSnapshot`, and computes their **personal bar**:

```
personalBar_i = round_to_increment( mu_i + k[difficulty] · sigma_i )
k             = { easy: 0.5, medium: 1.0, hard: 1.75 }    # per-metric, in config/flags
```

The three difficulty cards are quoted *before* queueing from the player's own numbers — a 1.50 K/D player sees roughly **Easy 1.60 / Medium 1.70 / Hard 1.80** (exact values depend on their `sigma`), never a bar built from a stranger's stats. Per-match performance is approximately normal around a player's mean, so at your own personal bar you clear with probability `1 − Φ(k)`: **≈31% on Easy, ≈16% on Medium, ≈4% on Hard**. Those target clear rates are printed on the card ("Hard — roughly 1 in 25 games at your level clears this bar"). That is *disclosed difficulty*, not odds: there is no payout line, the prize is only the entrants' pool minus rake, and nobody clears → **everyone refunded, zero rake** (the already-tested path).

**(c) Room formation — one room bar, the average of the members' personal bars.** A pool ticket is `(game, metric, difficulty, entry tier)`. The matcher groups `roomSize = 4` compatible tickets (config; falls to `minRoom = 3` at the end of the widening ladder) into a room and computes the single bar every member must clear:

```
roomBar = round_to_increment( mean(personalBar_1 … personalBar_m) )
```

This is the fairness mechanism the averaging exists for: since members are matched on similar stats, each personal bar is close to the average, and pooling them means nobody plays against a bar tuned to someone else's level — e.g. four Easy tickets with personal bars 1.60, 1.65, 1.62, 1.65 form a room with `roomBar = 1.63`, and the card shows exactly that derivation. **A group is only formed if the averaged bar stays fair for every member.** For each candidate member with model `(mu_i, sigma_i)`:

```
p_i = 1 − Φ( (roomBar − mu_i) / sigma_i )              # i's implied clear probability vs the room bar
form the room  iff  ∀i:  p_target / 2  ≤  p_i  ≤  min( 2 · p_target, 0.5 )
```

where `p_target` is the difficulty's design clear rate from (b). This is the v2 join-gate predicate promoted from *admission* to *composition*: a shark whose presence would drag the average down until the bar is trivial *for them* can't be grouped with weaker players (their own `p_i` breaches the cap), and a hopeless outlier can't be dragged upward. Additional composition guards: all members inside the ticket's current band tolerance (§4.5e ladder), `can_pair` across every member pair (§7), and a hard cap on personal-bar spread (`max − min ≤ spreadCap`, config) so the average is always an average of near-equals, not a compromise between extremes.

**Legibility on the room card:** the room bar, *your* personal bar at that difficulty, and the delta ("Room bar **1.71** — your Medium bar was 1.70"), plus each member's band. The player always sees why the number moved and by how much; both the personal bars and the average replay exactly from the frozen `baselineSnapshot`s in a dispute.

**Fill mechanics:** match-on-write — enqueueing when `roomSize − 1` compatible tickets are already waiting forms the room in one round trip; otherwise the widen cron relaxes tolerance on the §4.5(e) ladder. Past the ladder: offer (a) keep waiting, (b) start now with `minRoom` if that many compatible tickets exist, (c) cancel → instant refund; ticket TTL via watchdog guarantees no escrow is stranded. Settlement is unchanged from the tested path: clear = your qualifying game inside the window beats `roomBar`; clearers split pool − rake; nobody clears → full refund, zero rake.

**Friends-posted pools remain** as the one non-queued pool surface (`visibility: friends|direct`): the creator's personal bar *is* the pool bar, disclosed as such — consenting friends choose their own risk, same as the §5.2 band bypass. There is no public browse-and-join pool anymore; the queue is the only stranger path, which is what makes the averaged bar universal for strangers.

**(d) H2H stat duels — pair on predicted closeness, not adjacent stats.** A queue ticket is `(game, metric, stake tier)`. Model each candidate's next-match performance as independent normals, which gives a closed-form duel forecast:

```
P(a beats b) = Φ( (mu_a − mu_b) / sqrt(sigma_a² + sigma_b²) )
```

**Eligibility:** pair only if `P ∈ [0.5 − w, 0.5 + w]`, with `w` on the widening ladder in (e). Since stakes are always equal (no handicaps, no odds), *all* fairness must come from this window — that is why it starts tight. **Selection:** among eligible candidates, take the lowest composite score:

```
score(a,b) = 0.60 · |mu_a − mu_b| / sigma_pooled       # closeness on the wagered metric
           + 0.30 · d_z( vector_a, vector_b )          # overall skill-vector distance (ExactMatcher, §4.1)
           + 0.10 · |sigma_a − sigma_b| / sigma_pooled # consistency similarity
subject to can_pair(a, b)                              # §7: self/pair-cap/provisional checks
```

The 0.30 whole-profile term blocks the pathology where two players share a K/D reached by opposite styles (entry-fragger vs. anchor — same mean, different games); the 0.10 variance term avoids pairing a steady player with a boom-or-bust player, which is 50/50 on paper but feels like a coin flip to the steady one. The confirmation card shows the forecast honestly — "Even duel — model gives you 52%" — the peer-to-peer analog of rake disclosure. Resolution: higher frozen-window metric wins the pot; **exactly equal → push** (full refund, zero rake); the §6.2 forfeit/window rules cover the no-show cases.

**(e) Widening ladder — one schedule for duels, pool rooms, and tournament rooms, queue-depth aware.**

```
0–30s     w = 0.05  (accept 45–55% forecasts)   band ±0   room spreadCap ×1.0
30s–2min  w = 0.10  (40–60%)                    band ±1   spreadCap ×1.25
2–5min    w = 0.15  (35–65%)                    band ±2   spreadCap ×1.5   → notify "widening"
>5min     duels: keep waiting · convert to posted lobby contest · cancel + refund
          pool rooms: keep waiting · start at minRoom if fillable · cancel + refund
          tournaments: keep waiting · start at minField if fillable · cancel + refund
depth < K tickets in this (game, metric): start one rung wider
```

Match-on-write (§4.3) is unchanged — enqueueing pairs you instantly when a compatible ticket is already waiting; the widen cron only relaxes those left waiting. Every constant above (`k[]`, `w` ladder, tolerances, N, half-life, floors) lives in `config/flags`: calibration is a config change, not a deploy, and per-game tuning is expected (Dota performance is spikier than CS2; its starting `w` will differ).

**(f) Integrity hooks specific to metric wagering.**

- **Sandbagging is now the attack that pays** (a tanked baseline lowers your personal bar — which also drags the *room average* down — and softens your duels), so it gets a dedicated detector: recent-10 mean markedly below lifetime mean (z < −1.5) → risk flag, metric wagers blocked pending review. Deliberate-loss patterns in host history feed the same flag. Averaging adds a second face to watch: the shark who wants into rooms below their level so the averaged bar lands under their true ability — that is exactly what the (c) composition predicate (`p_i` cap) blocks, so a breach of it is enforced at formation, not detected after.
- **Frozen snapshots** (a) close the join-then-manipulate window and make every bar, room average, and pairing auditable after the fact — `roomBar` must reproduce byte-for-byte from the members' stored `baselineSnapshot`s.
- **The rate-metric allowlist** (a) is enforced server-side; a request naming any other metric is rejected — there is no surface on which a user or an operator can introduce a prop bet or a line. The room bar is likewise never client-supplied: tickets carry only `(game, metric, difficulty, tier)`; every number is server-derived.
- Pair caps, provisional floors, one-account-per-host-account, and band re-checks at formation time (§7) all apply unchanged — `can_pair` runs across every member pair of a pool or tournament room, so two colluding friends can't seed a room together past their cap.

### 4.6 Matchmade stat tournaments — ten similar players, one metric, top three paid

Tournaments get the same queue-first treatment as pools, and the format collapses to something async-native and brutally legible: **a room of similar-stat players all competing on a single metric; the three highest scores split the pot; everyone else loses their entry.**

**(a) Ticket and room formation.** A tournament ticket is `(game, metric, entry tier)` — no difficulty axis; the field itself is the difficulty. The matcher fills a room of `fieldSize = 10` (config; falls to `minField = 6` at the end of the §4.5e ladder). Composition guards, all server-side at formation:

- every member inside band tolerance of every other (ladder-widened, §4.5e);
- metric-`mu` dispersion cap: `max(mu) − min(mu) ≤ dispersionCap · sigma_pooled` (config, per game/metric) — because ranking is on **raw metric value**, the entire fairness burden sits on this cap, so it starts tight (≈1.0 pooled sigma) and is the tournament analog of the duel's 45–55% forecast window;
- among surplus candidates, selection minimizes total vector distance (the §4.5d whole-profile term, generalized to the group);
- `can_pair` across all member pairs; provisional metrics (`n < 10`) excluded as everywhere.

Entries are escrowed at enqueue; the room card shows the field's band range and the anonymized `mu` spread ("Field: K/D 1.42–1.58") so the fairness is displayed, not asserted. `baselineSnapshot`s freeze at enqueue as usual.

**(b) Scoring — first-N average, not best-of.** Each entrant's tournament score is the **mean of the metric over their first `N = 3` qualifying matches** (config) inside the window (48h default, config), graded from host data by the settle sweep. First-N — not best-single-match — so playing more games buys zero extra chances; the rule is printed on the card. Minimum one qualifying match to be ranked.

**(c) Settlement.** Rank by score descending; **top 3 split `pot − rake` per the prize table `50 / 30 / 20`** (config); ranks 4+ lose their entry. Ties at a paid boundary: standard competition ranking, tied players split the combined prize slices evenly (integer-cent remainders to the earlier finisher by enqueue time — deterministic, disclosed). Entrants with zero qualifying matches after window + grace rank below everyone who played (forfeit, stated up front — same §6.2 rule as duels). If fewer than `minRanked = 4` entrants play at all, the event is `CANCELED` — full refund, zero rake, the watchdog path. Conservation invariant per §3.1 applies unchanged: `sum(prizes) + rake == sum(entries)`.

**(d) Design note, held for calibration.** Ranking on raw value means the top of the admitted `mu` spread always has an edge bounded by the dispersion cap. If telemetry shows the same profile winning too often, the config-flag escape hatch is to switch scoring to the z-scored form `(score − mu_i) / sigma_i` (best performance *relative to your own baseline*) — fairer but less legible. Launch on raw value with a tight cap; decide with data, not by taste.

---

## 5. Friends & direct challenges

### 5.1 Adding friends

Two paths, both cheap and abuse-resistant:

- **Friend code** — every user gets a short immutable code (`MM-7F3K2Q`) shown in Profile; enter a code → request sent. Codes avoid a public username directory (no scraping/harassment surface).
- **Username search** — exact-match search on Money Match display name (not host-game accounts — don't leak account linkage), returns a single card → request.

Flow: `POST /api/friends/request` creates `friendRequests/{id}` + an inbox notification. Accept → server transaction writes the **mirrored edges** `users/{A}/friends/{B}` and `users/{B}/friends/{A}` (`status: accepted, since`), deletes the request. Decline/blocklist supported; blocked uids can't re-request or see your contests. Caps: 500 friends, 20 pending outbound requests (spam control). All writes server-side; edges are readable only by their owner.

### 5.2 What friendship unlocks

- **Direct challenge** — from a friend's card or profile: pick game/format/entry → contract created with `visibility: direct`, `invitedUids: [friend]`, entry escrowed. The friend gets an inbox item + (if online) a toast; accepting escrows their entry and activates. **Expires in 24h → automatic full refund** (watchdog-enforced, never stuck).
- **Friends-visible contests** — Builder gains a visibility toggle: `public` (banded feed) / `friends` / `direct`.
- **Band bypass with honesty** — friends may play across bands; the confirmation card shows the mismatch plainly ("You're Band 5, Jordan is Band 2 — heavily favored") rather than blocking. Fairness protection exists for strangers; consenting friends choose their own risk.
- **Social surfaces (light, Phase A):** friends' `lastSeenAt` presence dot, head-to-head lifetime record on the friend card (the per-opponent P&L data already exists in My Contests).

### 5.3 Feed integration

The client keeps the friend uid list in memory (≤500 ids), and the friends-feed query chunks it into `creatorUid in [...]` batches of 30. At our cap that's ≤17 reads per refresh — fine. If friend graphs ever grow past this, the standard fix is fan-out-on-write to a per-user feed; explicitly deferred.

### 5.4 Friends are the #1 collusion vector — say it and design for it

Two friendly accounts intentionally shuttling a pot is the obvious attack (and in Phase B, the chargeback accomplice pattern). Controls, all server-side in `can_pair` (the stub in `matchmaking.py` becomes real):

- **Rake-bearing contests between the same pair are capped** (e.g. 3/day, 10/week) — friends included.
- **Friendlies are unlimited but rake-free and leaderboard-excluded** (zero-rake mode, entry returned on settle in Phase A; in Phase B friendlies stay play-money). This removes the *economic motive* for pair collusion while keeping social play frictionless — the design insight is that collusion controls should bite money flow, not fun.
- **Directional-flow monitoring** (Phase B): net value moving one way inside a pair above a threshold → risk flag, withdrawal hold, review. Same device/IP/instrument clustering per roadmap §2.3.

---

## 6. Wagering feasibility & reliability review

An honest per-product assessment — what genuinely works, what has variance, and what changes.

### 6.1 Verdict table

| Product | Verdict | Why / what changes |
|---|---|---|
| **Chess H2H** | **Strong — flagship.** | Deterministic, host-verified, two-sided. Server creates a **Lichess open challenge restricted to the two linked usernames** (`POST /api/challenge/open` with `users=a,b`) — no OAuth needed at launch, both players click the same link, and settlement grades that specific game id (stronger than "next qualifying game" inference: no ambiguity about *which* game counts). Draws: **push** — full refund, no rake (simple, fair, legible; the bracket engine's rematch rule stays for tournaments). |
| **CS2 H2H** | **Feasible — the stat duel (§4.5d).** | Two arbitrary users can't be put into one FaceIt lobby, so the H2H objective is the **stat duel**: pick one rate metric (K/D, ADR, HS%…), equal stakes, higher value in each player's next FaceIt match wins; exactly equal → push. Fairness comes entirely from the §4.5(d) pairing (forecast held to 45–55% at tolerance 0), since equal stakes forbid handicaps. Cross-lobby variance is real — disclosed on the card ("separate matches") and bounded by the pairing window. **Accessibility caveat:** FaceIt players only (Premier/Valve MM invisible) — say so at link time. *Friends who can join the same FaceIt lobby* get the cleaner same-match objective as a fast-follow. |
| **Dota 2 H2H** | **Feasible — same stat-duel model (§4.5d), plus a data-visibility gate.** | OpenDota only sees players with **"Expose Public Match Data"** enabled. Enforce at link time: verify recent matches are readable; if not, block linking with instructions (not a silent later failure). Win/loss lands in OpenDota within minutes of match end; detailed stats can lag parsing — so v1 Dota duel metrics use only fast fields (KDA from the recent-matches endpoint; GPM once parse is confirmed), and the sweep treats "match visible but unparsed" as *pending*, never as *missed*. Dota's per-match variance is higher than CS2's — its duel window `w` starts wider (config, §4.5e). |
| **Solo pools** | **Feasible — queue-matched rooms with averaged bars (§4.5b–c); CS2 real today; chess metric swap; gate the rest.** | CS2 pools grade against real FaceIt telemetry already — the reference implementation. **Chess accuracy pools change metric:** engine accuracy requires Lichess server analysis which isn't reliably present per game; launch chess pools on **always-available facts** (win in ≤N moves, win streak, rating gained) and defer accuracy bars until OAuth + analysis requests. Dota pools on fast fields (K/D/A, GPM once parse confirmed). Games without a real telemetry path (Rocket League, Clash Royale) **do not ship** — a pool that can't verify is a refund machine plus a trust hole. **Pool bars are never user-chosen numbers:** each player's personal bar is server-computed from their own verified baseline at a picked difficulty, the room bar is the server-computed average of the matched members' bars, and the §4.5(c) composition predicate keeps every member's clear chance comparable — no odds-setting surface exists anywhere in the product. |
| **Tournaments** | **Ship matchmade stat tournaments (§4.6); hold real-user brackets.** | The §4.6 format is async-native (a matchmade field of ~10 similar-stat players; everyone plays their own games in a window; first-N average on one metric; top 3 split per prize table) — real users work with zero scheduling, and the tight `mu` dispersion cap carries the fairness. This subsumes the old open-join `leaderboard_pool`: same settlement engine, matchmade admission instead of self-selection. `single_elim` between real users needs round scheduling/forfeit handling — genuinely hard, low launch value; keep brackets as bot exhibitions or friends-only, revisit Phase B+. |
| **Leaderboard** | **Ships as-is** with real user records replacing the seeded field over time; ROI-ranked (not raw $), bots excluded. |

### 6.2 Failure-mode matrix (every row has a tested code path — this is the "fool-proof" section)

| Failure | Handling |
|---|---|
| Host API down / 5xx during settlement | Contract stays `RESOLVING`; sweep retries with backoff. Outage doesn't consume the window (`windowEnds` extends by downtime, per overview §3.3). Beyond a hard ceiling (24h) → `CANCELED`, full refund. |
| No qualifying game in the window | `CANCELED`, full refund, zero rake (existing behavior — kept). |
| Both CS2/Dota results identical / chess draw | **Push:** full refund, zero rake. |
| Opponent never plays (stat race, one-sided) | Player who played wins by forfeit **only after** the full window plus a disclosed grace period; card copy states the forfeit rule up front. |
| Player unlinks / host account banned mid-contract | Unlink is blocked while contracts are in flight (account-binding immutability); a host cheat-ban before settlement → contract `CANCELED` + refund + risk flag (post-settlement clawback is Phase B per user agreement). |
| Double-join race on a lobby contest | Firestore transaction on join: re-reads state, second joiner fails cleanly with "contest filled". |
| Settle cron double-fire / user spams "check now" | Idempotent transition: transaction no-ops unless state ∈ `ACTIVE|RESOLVING`. Fuzz-tested. |
| Duplicate / out-of-order Stripe webhook | `stripeEvents/{event.id}` create-once marker inside the posting transaction → exactly-once ledger effect. |
| Queue ticket orphaned (user closes tab) | Ticket TTL; watchdog cancels + refunds. Same for expired direct challenges. |
| Pool/tournament room never fills | Ladder exhausts → offer start-at-minimum (`minRoom`/`minField`) or cancel; ticket TTL → watchdog cancels + refunds. A room is never formed below the minimum; escrow is never stranded in a dead queue. |
| Tournament entrant plays zero qualifying matches | Ranked below all entrants who played, after window + grace (forfeit rule disclosed on the card). Fewer than `minRanked` entrants play at all → event `CANCELED`, full refund, zero rake. |
| Room bar / field disputed after settlement | `roomBar`, every `personalBar`, and the `mu` spread replay deterministically from the members' frozen `baselineSnapshot`s — the audit is a pure-function re-run, not an investigation. |
| Ledger drift / invariant breach | Nightly audit cron (§3.4): alert + auto-flip joins/deposits kill switches. Fail closed. |
| Wrong-server-on-port / stale deploy classes of bugs | Health endpoint asserts registered adapters + flags doc version; smoke test in CI post-deploy. |

**The watchdog cron** is the unifying reliability idea: every non-terminal state (`OPEN` lobby, queue ticket, `MATCHED` awaiting confirm, `RESOLVING`, `PENDING` payout, direct challenge) carries a max age, and the watchdog's only job is *no object is ever stuck and no cent is ever stranded in escrow*. Everything it touches resolves toward refund, never toward loss.

---

## 7. Security (delta from v1, Stripe-aware)

1. **Firebase Auth on every route** (`verify_id_token` dependency); identity = token uid + server-stored links. Zero trust in client-sent usernames or amounts.
2. **Server computes all money**; entries from fixed tier enums; objectives from typed unions; Pydantic end-to-end.
3. **Firestore rules** per §2.1, emulator-tested in CI.
4. **Prod-gate the demo surfaces**: `api/_lib/demo/routes.py` (manual outcome buttons!) and `/api/dev/faceit/*` 404 when `VERCEL_ENV == "production"`, with a pytest asserting it.
5. **Stripe-specific:** webhook signature verification + event-id dedupe (§3.2); Checkout-hosted card entry (PCI SAQ-A); Radar with velocity rules; deposit tiers + per-user daily deposit caps; 48–72h withdrawal hold on fresh deposits; payout only to Stripe-verified (KYC'd) connected accounts; secret keys only in Vercel env; **live keys do not exist until the Phase B gate**.
6. **Limits enforced server-side against the ledger** — daily loss cap, daily entry cap, max simultaneous contests (overview §7.3). This replaces (and fixes) the known client no-op in `useWallet.canJoin` (IMPLEMENTATION.md §14.1).
7. **`can_pair` becomes real:** self-pair block (uid *and* host account *and* device fingerprint), pair-frequency caps (friends included, §5.4), provisional-account floor (§4.1), one Money Match account per host account (uniqueness on links).
8. **Rate limiting** on create/join/queue/link/settle-now/friend-request (per-uid Firestore counters; Upstash Redis if we outgrow them) — also protects host API quotas.
9. **Overlay:** read-only scope, revocable device token via `safeStorage`, `contextIsolation` + `sandbox`; a stolen overlay token can leak a wager card, never move money.
10. **Hygiene:** CORS pinned to prod origins (env-driven); `git log -p -- .env` secret audit before going public; geo-list parity test (`states.ts` ↔ `solo_challenge.py`); 18+/residence attestation stored on the user doc; Sentry on both tiers; GCP + Stripe test-mode budget/anomaly alerts.

---

## 8. Scalability & sustainability (updated)

Host API quotas remain the true bottleneck; the money system adds reconciliation duties.

- **Quota reality:** Lichess (per-IP limits, heavy NDJSON), FaceIt (keyed, per-key limits — verify production tier before launch day), OpenDota (~2,000 calls/day free, 60/min). Mitigations: read-through `cache/{key}` collection in all three service clients (profiles 1h TTL; **finished matches are immutable — cache forever**); settlement sweep batches by `(game, accountId)` so one host call settles all of a player's contracts; rate limits upstream of everything. Move FaceIt's in-proc cache to Firestore — serverless instances share nothing (same audit kills `demo/store.py` assumptions).
- **Firestore shape:** append-only random-id ledger (no hot spots); per-uid wallet docs; composite indexes for the banded feed committed in `firestore.indexes.json`; `onSnapshot` gives the lobby/wallet real-time updates for free.
- **Crons (Vercel, ≥1/min):** settle-sweep, match-widen, watchdog, nightly reconcile + skill refresh. All idempotent; all safe to double-fire; all protected by a cron secret.
- **Cost ceiling at launch scale:** Firestore free tier + Vercel Pro (~$20/mo) + $0 host APIs + Stripe test mode $0. Budget alert at $25.
- **Sustainability:** CI = pytest + rules-emulator tests + `tsc` + `vite build` + the no-odds-vocabulary grep gate; Vitest on money-display components and the join flow; single `post_ledger()` choke point (no other wallet writes, enforced by review + a grep in CI); kill switches in `config/flags` (per-game, joins, deposits, withdrawals, overlay) readable per-request — disable anything without a deploy; README replaces the one-liner; **naming unification now** (repo `clutchbook` / brand "money match" / overlay URL `clutchbook.app` → one public name + domain before anything is published, and before the Stripe application, which requires a real business identity and website).

---

## 9. The overlay (unchanged in substance from v1)

Keep Electron for v1 (detector + transparent window already work; Tauri is a post-launch diet). The rewire: delete the legacy odds card (`getWagerForGame.ts`, `ContractContent`) → render the contest shape (objective, entry, pot, rake, prize, countdown, state); pair via a revocable read-only device token generated in Profile (stored via `safeStorage`); one endpoint `GET /api/overlay/active?game=` returning the most relevant in-flight contract **for the focused game only** (detector title → adapter id mapping; CS2/Dota are the overlay's real targets since chess is browser-played); poll 15–30s while a game window is focused, hide otherwise; fix the hardcoded prod URL; package with `electron-builder` + `electron-updater`, distribute via GitHub Releases linked from Profile (unsigned SmartScreen warning is acceptable for beta and disclosed in the download UI). A "match found" toast from the inbox feed is a cheap, high-delight addition while a game is focused.

---

## 10. Build plan

Assumes ~2 people. **Bold = cut-line critical path.** Phase A ships publicly at the end of week 2; Phase B is gated, not dated by wish.

### Phase A, Week 1 — trust moves to the server

| Day | Work |
|---|---|
| 1 | Firebase project; Auth; Firestore + rules skeleton; **verify-token dependency on every route**; service account into Vercel env. **Submit the Stripe restricted-business application** (skill-contest memo, business identity, the public domain). Pick the public name/domain (blocks the application — do it first). |
| 2 | **Ledger + wallets:** promote `demo/ledger.py` to the production `post_ledger()` (chart of accounts §3.1); wallet docs as derived cache; promo-funded starting bankroll on first sign-in; nightly audit cron skeleton. Account-link endpoints with the Dota expose-data check and CS2 FaceIt-account checks; links immutable. |
| 3 | **Contracts + lobby server-side:** create/join/cancel with transactional escrow; banded visibility fields + indexes; join-side predicate enforcement; `can_pair` v1 (self-pair, pair caps, provisional floor). Skill docs (`skillScore`/band/vector) + per-metric models (`mu`/`sigma`/`n`, §4.5a) computed on link. |
| 4 | **Settlement server-side:** adapter-grouped settle-sweep cron (port the client poller's grouping); idempotent transitions + double-fire fuzz test; watchdog cron (ticket/challenge/lobby TTLs, stuck-state refunds); chess switches to restricted open-challenge grading; CS2/Dota stat-race objectives + push rules. |
| 5 | **Frontend migration:** `useWallet`/`useContracts` → `onSnapshot` + API mutations; sign-in replaces the mock gate (residence + 18+ persisted); banded lobby feed; Builder visibility toggle. |
| w/e | Buffer: pool + tournament settlement onto the same server-side pattern — room-bar grading against real telemetry (CS2 first; chess metric swap), first-N tournament scoring + prize-table split + tie handling; delete dead code (`useContracts.lobby`, `Sparkline`, `stub_cs2`). |

### Phase A, Week 2 — matchmaking polish, friends, overlay, publish

| Day | Work |
|---|---|
| 6 | **Quick match + room formation:** one ticket schema for duels/pools/tournaments, match-on-write transaction with the §4.5(d) duel-forecast eligibility + composite selection, widen cron (§4.5e ladder), give-up paths, bot practice fill; pool personal-bar derivation at enqueue + room formation with averaged `roomBar` + composition predicate (§4.5b–c); tournament field formation with `mu`-dispersion cap (§4.6a); room/field confirmation cards (room bar delta, field spread, duel forecast); sandbagging detector v1 (§4.5f). |
| 7 | **Friends:** codes, requests, mirrored edges, direct challenges with expiry-refund, friends feed query, friendly (zero-rake) mode; inbox notifications wired to toasts. |
| 8 | **Overlay rewire + packaging** (§9). **Stripe test mode:** `StripeProvider` (Checkout, webhook dedupe, ledger postings), deposits/withdrawals behind `flags` — exercised in staging, disabled in prod. |
| 9 | **Security + sustainability pass:** rules emulator tests, prod-gating tests for demo/dev routes, rate limits, server-side limits, CORS, CI + Sentry + kill switches + README + secret audit. |
| 10 | **Dress rehearsal on staging:** two real humans × three games — quick match, lobby join, friend challenge, solo pool, settle, ledger audit green; overlay shows the CS2/Dota wager in-game. Fix fallout. |
| w/e | **Publish:** prod domain, rules deploy, overlay release, single-community launch. Checklist below. |

### Phase B (weeks 3–6, every gate must pass — no dates promised on approvals)

1. **Stripe approval** received for real-money skill contests (else: execute the PSP fallback via `PaymentProvider`).
2. **Counsel sign-off** on the P2P + pooled structures for the launch-state list; geolocation partner integrated (GPS-grade, not IP-only); excluded-state enforcement live.
3. **Connect Express onboarding** (KYC) + live deposits/withdrawals + holds + Radar rules + chargeback runbook; reconciliation running against live data for ≥1 week of internal-only real money before public enablement.
4. **Ownership-proof account linking** (real-money prerequisite — username claim is spoofable): Lichess OAuth; Steam OpenID (proves Dota + Steam identity); FaceIt Connect OAuth for CS2.
5. Directional-flow collusion monitoring + risk dashboard; dispute/support process staffed; ToS/privacy from counsel; 1099 config.
6. Real money enabled **per game, per state, behind flags**, chess first (cleanest skill story), CS2/Dota after the stat-race variance review.

### Phase A launch checklist (all must be true)

- [ ] Two real accounts complete a full contest on each of chess/CS2/Dota (quick match *and* lobby join *and* friend challenge) with zero manual intervention; ledger conservation + solvency audits green.
- [ ] A pool room forms from the queue at `minRoom`, its `roomBar` equals the rounded mean of the members' personal bars, and the room card shows each member's bar delta; a tournament field forms, settles on first-N scores, and pays exactly the 50/30/20 table (tie case exercised).
- [ ] A signed-out or tampered request can neither read nor mutate anyone's state (rules + API tests).
- [ ] Demo/dev endpoints 404 in production (tested). No live Stripe keys exist anywhere.
- [ ] Settlement double-fire test green; watchdog demonstrably un-sticks an orphaned ticket, an expired challenge, and a `RESOLVING` contract during the rehearsal.
- [ ] Band gating enforced server-side on join (hand-crafted cross-band join request rejected); the §4.5(c) composition predicate refuses to form a room containing a shark or a hopeless outlier in the rehearsal; the §4.6(a) dispersion cap refuses a lopsided tournament field; a duel pairing outside the §4.5(d) window cannot be forced via a crafted request.
- [ ] `roomBar` and every personal bar verifiably reproduce from the frozen `baselineSnapshot`s (audit replay), and no API surface accepts a user-supplied bar, room bar, line, or payout number.
- [ ] Overlay: clean-machine install → pair → shows the active CS2 wager in-game; shows nothing for a game with no wager; token revocation works.
- [ ] Kill switches flip without deploys; Sentry receiving from both tiers; budget alerts set; grep gate green (the overlay rewrite clears the last "house edge" strings).

---

## 11. Top risks

1. **Stripe declines the restricted-business application.** Likelihood: real. Blast radius: Phase B timing only — Phase A doesn't depend on it, and the `PaymentProvider` seam plus named PSP fallbacks (Nuvei/Paysafe/Aeropay/Trustly) is the mitigation. Do not touch live keys before written approval.
2. **Cold-start liquidity, worsened by banding — and now by room fill.** Duels need 2 compatible players; pool rooms need 3–4; tournament fields need 6–10 — the queue-matched formats are strictly hungrier than v2's open-join pools. Mitigations: single-community launch, fast widening at low depth, the start-at-minimum give-up path (`minRoom = 3`, `minField = 6`), friends bypass, labeled bot practice. Accept that week-one tournament fields may rarely fill; the design degrades to "duels + friends-posted pools," which still works. Do not respond by loosening the composition guards — thin-but-fair beats full-but-rigged.
3. **Stat-race variance sours CS2/Dota H2H.** Disclosed on the card, push rules, banded opponents, play-money stakes. Watch dispute/complaint telemetry; if it's bad, bias CS2/Dota toward solo pools and leaderboard tournaments (which have no cross-lobby variance) before Phase B.
4. **Host API dependency:** FaceIt key tier unverified → verify before launch day; OpenDota quota → cache + batch are on the critical path; any host outage → the §6.2 refund paths, never stuck money.
5. **Scope creep into real money before the gates.** The play-money line is the legal firewall *and* the Stripe-account-survival firewall. It is crossed only through the Phase B gate list, in order.

---

## 12. What this buys us

At the end of Phase A: a real multiplayer product — accounts, fair banded matchmaking with a seconds-fast quick match, friends and direct challenges, three games settling against real match data, an in-game overlay — on an architecture where the bank is an audited double-entry ledger, every money path is server-authoritative and idempotent, and Stripe is a config flip + an approval letter away. Phase B then adds money to a system that has already been running the money machinery for weeks, rather than adding the machinery under the pressure of live dollars.
