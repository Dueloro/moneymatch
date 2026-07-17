# Money Match: Product Overview

**Last updated:** 2026-07-15 (migrated from the PoC repo `clutchbook`)

> **Migration note.** The product definition, legal frame, and money mechanics
> here are current and normative for the MVP. Sections describing the *demo
> architecture* (§8) describe the **PoC**; the MVP architecture now lives in
> [`../implementation-guide/01-architecture.md`](../implementation-guide/01-architecture.md).
> Code paths of the form `api/…` / `src/…` refer to the PoC and resolve in this
> repo under [`/poc-reference`](../../poc-reference/) (`poc-reference/api/…`,
> `poc-reference/frontend/src/…`).

> Companion documents: [`roadmap.md`](./roadmap.md) (the master plan: demo → no-money MVP → gems → real money) and the research set indexed in [`README.md`](../README.md) — [`legal-compliance.md`](../legal/legal-compliance.md), [`integrity-audit.md`](../legal/integrity-audit.md), [`business-and-competition.md`](../business/business-and-competition.md), [`gtm-prelaunch.md`](../business/gtm-prelaunch.md). Read this file first for product definition.
>
> The pre-pivot docs (sportsbook framing, house-banked "Clutchbook" contracts, corp/data notes) remain archived in the PoC repo under `clutchbook/docs/old/`. They are deprecated and were not migrated.

---

## 1. Summary

**Money Match is a peer-to-peer skill-wagering platform layered on top of games people already play.** Two (or more) verified players stake an equal entry fee into an escrowed pot, each plays a real match on a connected game, results are auto-verified through that game's official API, and the winner takes the pot **minus a fixed platform rake**. Money Match never wins or loses on the outcome of a contest — our only revenue is the rake.

We intend to launch with Chess via Lichess. Chess is as close to a pure game of skill as exists. Lichess has a mature free public API, a deeply rated player base, and strong built-in anti-cheat. The platform is built game-agnostic so additional titles with open APIs (Counter-Strike 2, Clash Royale, Rocket League, etc.) plug in as new game adapters without re-architecting the matchmaking, escrow, settlement, or rake layers.

The model is directly inspired by **Triumph (Triumph Labs) "Play for Cash"** and **Skillz** — real-money skill-contest platforms that operate legally in ~40 U.S. states. The difference is that Triumph and Skillz run *in-house* games they fully control. Money Match runs the same legal structure **on top of existing competitive games**, which is the differentiation and, as [§6](#6-fair-play-collusion-and-cheating) explains, the main thing we have to engineer around.

---

## 2. Why Peer-to-Peer

This is the single most important decision in the product.

**Gambling, legally, requires three elements simultaneously: (1) consideration, (2) chance, and (3) prize.** Remove any one and the activity is, by definition, not gambling. Skill-contest operators work by removing **chance**, so the outcome is determined by the players' measurable skill, which courts test under the "predominance of skill" / dominant-factor standard.

But *how* the money flows matters just as much as the skill test:

| Axis | House-banked model (what we do NOT do) | Peer-to-peer + rake (what money match IS) |
| --- | --- | --- |
| Structure | User wagers against a line the platform sets | Players stake into a shared pot |
| Platform's stake in the outcome | House profits when the user loses (margin baked into odds) | House has **zero** stake in who wins |
| How the platform earns | The spread / vig | A **fixed rake** taken off the pot regardless of who wins |
| What it legally resembles | A sportsbook / proposition bet | A contest of skill (poker rake, DFS, Skillz, Triumph) |

A "wager against the house's line" — even a skill-derived one — **is a proposition bet**, which is the sportsbook framing we are explicitly leaving behind. The defensible structure, the one that operates in ~40 states today, is **peer-to-peer entry-fee contests where the platform is a neutral operator taking only a rake.** money match commits to that structure as its legal and revenue core.

### 2.1 What money match is NOT

- **Not a sportsbook.** Players never wager against a house line and never wager on third parties' matches. Every contest resolves on the entrants' own play.
- **Not a casino.** Outcomes are determined by measurable skilled performance in a deterministic-rules game, not by RNG.
- **Not fantasy / DFS.** There is no roster construction, salary cap, or proxy contest — you compete with your own live play.
- **Not house-banked.** money match is a neutral operator. It does not take a position against its users.

---

## 3. The skill contract

A **skill contract** is the atomic unit of money match: a structured, escrowed agreement between two or more players to compete on a measurable objective for a pot.

> "We each stake **{entry}**. Whoever **{wins / best achieves the objective}** in **{game / format}** within **{window}** takes the pot of **{N × entry}**, minus money match's **{rake}**."

A contract has these required fields:

| Field | Example |
| --- | --- |
| `game` | `chess.lichess` |
| `format` | Rated Blitz 5+0 |
| `objective` | Win the head-to-head game |
| `entrants` | 2 (head-to-head) … N (pooled contest) |
| `entry` | Per-player stake, e.g. $5 (Phase-1 caps — see [§7](#7-money-mechanics)) |
| `window` | The qualifying game(s) / time budget the contract resolves within |
| `rake_pct` | Fixed platform fee on the pot, e.g. 10% |
| `pot` / `prize` | `entrants × entry`; winner receives `pot × (1 − rake_pct)` |

The platform sets and discloses the rake; it does **not** price odds against the player. Skill-bracketed matchmaking (not odds) is how fairness is created: players are paired within a rating band so each contest is a genuine contest.

### 3.1 Contract types

Three families ship, in priority order by legal cleanliness:

1. **Head-to-head match (primary).** Two players, paired by skill bracket, play a single game (a Lichess challenge generated under the hood). Winner takes the pot minus rake. *Cleanest legally — both players are trying to win the same game, which suppresses collusion and is the strongest skill-predominance story.*

2. **Multi-entrant skill tournament.** N players each play their own qualifying game(s); ranked by an objective metric (win, fewest moves, rating gained). Top finishers split the prize pool minus rake. Mirrors the Skillz/Triumph bracket format.

3. **Benchmark / solo challenge (play-money only in production until cleared).** A single player attempts an objective against a stat-derived benchmark. **This is the one family that risks looking house-banked**, so in production it is either (a) restructured as a pooled contest against other solo entrants, or (b) kept play-money-only. It is never offered as a real-money wager against the house. See [§8.1](#81-the-existing-demo-is-a-house-banked-simplification) and the **Algorithmic Solo Challenges** feature in [§10](#10-algorithmic-solo-challenges-pooled), which resolves this tension with a pooled, rake-only structure (no house).

### 3.2 Matchmaking, not odds

Because money match is peer-to-peer, the engine's job is **pairing**, not pricing. The matchmaking service keys on `(game, format, entry tier, rating band)` and widens the rating tolerance over time until a fair match is found. The former "odds engine" is repurposed into a **skill-rating + bracketing service**: it estimates each player's strength to bracket them and to surface an honest "you're well-matched / this is a reach" signal — it does **not** set a payout line. (Implementation home: `api/_lib/skill_rating.py` in the PoC; `services/skill_rating.py` in the MVP.)

### 3.3 Contract lifecycle

`OPEN → MATCHED → ACTIVE → RESOLVING → SETTLED` (or `CANCELED`).

- **OPEN** — a player has posted/queued an entry; stake reserved, not yet committed against an opponent.
- **MATCHED** — opponent(s) found and confirmed; all entries escrowed into the pot.
- **ACTIVE** — the qualifying game(s) are underway.
- **RESOLVING** — game(s) complete; confirming results via the host API. Typically sub-minute.
- **SETTLED** — outcome verified; winner credited `pot × (1 − rake)`, rake ledgered, receipts issued.
- **CANCELED** — no match found in the window, a game aborted before move 1, or a host outage: **all entries refunded in full** (a refund event, never a loss).

A game qualifies only if it matches the contract's `game`, `format`, and match-type filters and is between the matched accounts (for head-to-head). Aborts before move 1, games vs. banned/cheat-flagged accounts, and outages do not consume the window.

---

## 4. User experience — high level

### 4.1 Lobby (primary surface)

A feed of **open contests** the player can join, plus quick-join tiles by game/format/entry tier. One tap stakes an entry and drops the player into matchmaking. The honest queue UI shows the rating band being searched and an estimated wait derived from real queue depth.

### 4.2 Builder (power feature)

Lets a player post their own contest within allowed dimensions — game, format, objective from a typed list, entrant count, entry tier — which then sits in the lobby for others to join. Every posted contest still flows through the contract grammar and skill-bracket rules; it is not an open-ended request box.

### 4.3 Match & settle

On match, both players get a **Go play** affordance (deep link to the Lichess challenge / quick pairing). They play normally; money match polls the host API for the qualifying result. On completion the contract resolves and the pot settles with an animated payout and a receipt in **My Contests**.

---

## 5. Identity & verification

Every paid feature requires a verified identity bound to the host-game account whose play resolves the contest. Non-negotiable for fairness, anti-collusion, and compliance.

- **Lichess OAuth (primary / production path).** Verified `user.id` + scoped read of game history; required to issue challenges in head-to-head.
- **Username claim (fallback / demo).** Public-stats-only; reduced limits until upgraded to OAuth.
- **Account-binding immutability.** Once a host account is bound to a money match user, rebinding requires support intervention — this prevents stat-laundering and alt-account collusion.
- **Result verification is host-authoritative.** The client never reports its own outcome; settlement reads the game from the host API (`/api/games/user/{username}` filtered to qualifying games since `matched_at` for chess).

---

## 6. Fair play, collusion, and cheating

This is the part Triumph and Skillz get "for free" that we do not. They run in-house games on infrastructure they own; we run on third-party games. That gives us a better skill-predominance story (chess is purer skill than most casual mobile games) but a **harder integrity problem**: the platform does not control the game environment, so the principal risks are **collusion** (two accounts agree to fix the result and split the pot, dodging the rake or laundering value) and **cheating** (engine assistance, sandbagging to drop a rating band).

Mitigations, layered:

1. **Prefer head-to-head over solo objectives.** When both staked players are trying to win the *same* game, a thrown game costs the thrower the pot — collusion only works if they're moving money between their own accounts, which the controls below target.
2. **Host anti-cheat reliance.** Lichess flags suspicious accuracy distributions and bans engine users; we honor host flags and can claw back settled payouts on a post-hoc host cheat flag per the user agreement.
3. **Anti-collusion analytics.** Pair-frequency limits (no repeatedly matching the same two accounts), payment-instrument and device clustering, win/loss-flow analysis to detect value moving in one direction between a pair.
4. **Account thresholds.** Minimum account age and games-played before real-money contests unlock; rating-band integrity checks to catch sandbagging.
5. **Identity binding + geofencing** (see [§5](#5-identity--verification), [§9.2](#92-jurisdiction-strategy)) so one human cannot field both sides of a match.

We do not build our own chess anti-cheat; we build the **collusion and matchmaking-integrity** layer that the peer-to-peer-on-third-party-games model uniquely requires.

---

## 7. Money mechanics

money match handles real money at launch (the demo is a play-money sandbox — see [§8](#8-architecture)). Because the model is peer-to-peer, the money flows are an **escrow + rake**, not a book.

### 7.1 Wallet & escrow

Every verified user has a wallet with **available**, **pending** (entries escrowed in OPEN/MATCHED/ACTIVE contests), and **locked** (KYC / withdrawal / compliance hold) balances. On match, each entry moves available → escrow. On settlement, the pot pays the winner (escrow → winner available) and the rake is extracted to the platform ledger. Cancellations return escrow → available.

**Invariant, always:** `sum(payouts) + rake = sum(entries)`. The platform's books never carry outcome risk — only the rake accrues to money match.

### 7.2 Revenue: the rake

Primary revenue is a **fixed, disclosed rake** on each settled pot (configurable per game / format / contest type). This is the poker-room / Skillz / Triumph model: transparent to engineering (a single parameter), transparent to legal (we are a neutral operator charging a service fee, not a counterparty), and it generalizes to every contest type without the platform taking a position.

Secondary paths (not committed for Phase 1): premium tournament formats behind subscription, sponsored / branded contests tied to live events, seasonal leaderboard pools.

### 7.3 Limits (Phase-1 launch caps; schema load-bearing, values tunable by risk/compliance)

| Limit | Phase-1 value | Why |
| --- | --- | --- |
| Per-contest minimum entry | $1 | Low barrier to first contest. |
| Per-contest maximum entry | $100 | Caps single-contest exposure pre-KYC. |
| Daily loss cap (user) | $200 | Responsible-gaming control; user-lowerable. |
| Daily entry cap (user) | $500 | Velocity limit pre-KYC. |
| KYC-required threshold | $500 cumulative entries | Triggers identity verification. |
| Withdrawal minimum | $20 | Reduces processing overhead. |
| Max simultaneous open/active contests | 3 | Caps exposure and simplifies UX. |

### 7.4 Deposits & withdrawals

Out of scope for the demo. The production milestone (see roadmap) implements deposits via a regulated payments partner with a gaming-licensed correspondent, instant cash-out à la Triumph (Venmo / debit / PayPal / ACH), with same-instrument-in / same-instrument-out as the AML default.

---

## 8. Architecture

### 8.1 The existing demo is a house-banked simplification

The current shipped demo is **single-player, house-banked, play-money** (you accept a stat-derived "contract" against the platform). That framing predates this pivot and is **deprecated**. It survives only as a UX/data-pipeline sandbox. The roadmap carries a milestone to re-architect it into the peer-to-peer head-to-head model described here. Until then, treat the demo as a play-money prototype of the *surfaces*, not of the *legal/economic model*.

### 8.2 Current stack (carried into the demo)

React 18 + TypeScript + Vite frontend; FastAPI on Vercel Python backend; client-side state in `localStorage`. Right scope for a demo: fast to iterate, cheap to throw away. Modules that survive the pivot (renamed/reshaped):

- `api/_lib/skill_rating.py` → skill-rating + bracketing service (no longer prices odds).
- `api/_lib/lichess_service.py` / `adapters/chess_lichess.py` → the chess GameAdapter (reads + challenge issuance).
- `src/hooks/useWallet.ts`, `useContracts.ts` → escrow-aware wallet + contest lifecycle.
- Layout / UI shell — mostly reusable; copy and labels change from "contract vs line" to "contest / pot / rake."

### 8.3 GameAdapter interface (game-agnostic from day one)

```ts
interface GameAdapter {
  id: string;                                  // e.g. "chess.lichess"
  metadata: GameMetadata;                      // display, supported formats
  linkAccount(method: 'oauth' | 'username'): Promise<AccountLink>;
  fetchProfile(accountId: string): Promise<SkillProfile>;   // for bracketing
  createMatch(a: AccountLink, b: AccountLink, format: Format): Promise<MatchHandle>; // P2P challenge
  pollEligibleGames(accountId: string, since: Date, filters: GameFilters): Promise<Game[]>;
  resolveContract(contract: Contract, games: Game[]): ResolutionResult;
}
```

Matchmaking, escrow/rake, settlement, and the UI shell are written against this interface. Adding CS2 means writing `cs2.steam` — not refactoring core. Adapters register through `api/_lib/adapters/registry.py`. Chess is the only registered adapter; a CS2 stub proves the seam compiles.

### 8.4 Production architecture (forward-looking)

The production milestone between the demo and real-money launch introduces: **Postgres** (users, accounts, contracts, wallets, ledger); a **server-side matchmaking queue** (Redis/Postgres-backed); **two-sided escrow** with explicit rake extraction; an **append-only audit ledger** (every wallet mutation + state change — the source of truth for disputes/regulators); **Lichess OAuth** with refresh rotation and challenge scope; a **background settlement worker** replacing client polling; **payments + KYC partners**; and **per-game / per-user kill switches** operable without a deploy.

### 8.5 What stays game-specific vs. shared

| Layer | Game-specific? | Notes |
| --- | --- | --- |
| Account linking | Yes | OAuth varies per platform. |
| Profile / stat schema | Yes | Per-game normalized schema. |
| Match creation (challenge) | Yes | Each adapter knows its API. |
| Game polling | Yes | Each adapter knows its API. |
| Contract object (contest / pot / rake) | Shared | Universal. |
| Matchmaking & bracketing | Shared core + per-game calibration | Rating tables per game. |
| Escrow / wallet / rake / KYC / payouts | Shared | |
| Settlement state machine | Shared | |
| Anti-collusion analytics | Shared core + per-game signals | |
| UI shell | Shared | |
| Game card / detail surface | Themed per game | Same primitives, different visuals. |

---

## 9. Compliance & legal positioning

> Not legal advice. This is the team's working model — sufficient to make consistent decisions and to brief specialist counsel. **Every numeric limit, threshold, jurisdiction, and structural claim here must be validated by gaming counsel before any real-money launch.**

### 9.1 The skill-contest frame

money match operates under the **peer-to-peer contest-of-skill** frame established by Skillz, Triumph, online poker, and DFS operators. The argument has two legs that must *both* hold:

1. **Skill predominates over chance** (kills the "chance" element of gambling). Chess is a near-ideal anchor; each later title is assessed individually under the dominant-factor / material-element / any-chance tests, since states differ.
2. **The platform is a neutral operator, not a counterparty** (we charge a rake, we do not bank the action). This is why the [§2](#2-why-peer-to-peer--rake-and-not-a-sportsbook) structure is load-bearing, not cosmetic.

This dictates how we describe the product (we host *contests of skill*; we are not a *book*), how contracts are built (no contest may resolve on a purely random outcome; no contest is a wager against the house), and where we can operate.

### 9.2 Jurisdiction strategy

We do not launch nationally on day one. We mirror the established skill-contest geofence:

1. **Geofenced cash play in skill-permitted states** using a recognized geolocation partner (not IP-only), the way Skillz uses GPS verification.
2. **Hard-excluded states** — the operating geo-fence baseline (to be confirmed with counsel), the **14 "Any Chance" states** also enforced by the client gate (`src/components/Onboarding/Landing.tsx`) and the solo-challenge engine (`api/_lib/solo_challenge.py`): **Arizona, Arkansas, Connecticut, Delaware, Florida, Indiana, Louisiana, Maryland, Minnesota, Montana, South Carolina, South Dakota, Tennessee, Wyoming**. South Carolina is the strictest signal: courts there have indicated that where a *wager* is involved, the level of skill is irrelevant. Free-to-play remains available everywhere.
3. **Massachusetts is a launch state.** MA prohibits online *casino* gaming but permits skill-predominant contests and regulates DFS; Skillz and Triumph both run cash play in MA. money match's MA posture rides the contest-of-skill + neutral-operator frame, with the AG's DFS/contest regulations as the reference point. (Confirm current MA bill activity at launch — there is pending iGaming legislation that could reshape the landscape.)
4. **International** deferred until the U.S. footprint is stable; each country is its own compliance project.

### 9.3 KYC / AML

Triggered at the [§7.3](#73-limits-phase-1-launch-caps-schema-load-bearing-values-tunable-by-riskcompliance) threshold. Controls: same-instrument-in/out default, velocity monitoring on deposits/entries/withdrawals, sanctions screening at KYC, and SAR capability built into the audit ledger.

### 9.4 Responsible gaming (from production launch)

Self-set deposit/loss/session limits (lowerable instantly, raisable only after a 24h cooldown); self-exclusion (7-day minimum to permanent); reality-check session prompts; and a clear, accurate display of the **rake** on every contest so players always see what they are paying.

### 9.5 Open compliance items

Final state list and per-state nuance; KYC partner; payments partner with gaming-licensed correspondent; state registration/licensing where required; ToS / privacy / user agreement (counsel); the collusion-and-disputes process beyond automated host verification; tax reporting (1099 thresholds). The **collusion exposure unique to layering on third-party games** ([§6](#6-fair-play-collusion-and-cheating)) is the item most likely to need bespoke legal and risk attention versus the in-house-game precedents.

---

## 10. Algorithmic Solo Challenges (pooled)

> **Status: play-money in the demo; counsel sign-off required before real money (the §9 disclaimer applies in full).** The structure is committed: **pooled, rake-only, no house.** This is the same neutral-operator model as the peer-to-peer side ([§2](#2-why-peer-to-peer), [§7.1](#71-wallet--escrow)) — there is deliberately **no house-banked / guaranteed-prize variant**, because that would put the platform on the other side of the wager (see §10.4).

A **solo challenge** lets a player wager on *their own* measurable performance instead of against a specific opponent — but the prize still comes from a **shared pool of entrants**, never from the platform. Players each pay an equal entry into a pool for a given game + **qualifying skill standard** (a stat threshold — not a win/loss, not a prediction); everyone plays their own game; entrants who clear the standard split the pool **minus a fixed rake**.

### 10.1 Framework — pooled escrow, rake-only

```
N players each pay the same entry fee
   ➔ entries escrow into a shared prize pool
   ➔ platform verifies each player's game-API telemetry against the qualifying standard
   ➔ everyone who CLEARS the standard splits (pool − rake); nobody clears ➔ full refund
```

Why this is compliant, on two legs (both must hold — see [§9.1](#91-the-skill-contest-frame)):

1. **Skill predominates over chance.** The standard is a skill-attributable metric (§10.2); under the Predominant Factor Test the *chance* element is removed.
2. **The platform is a neutral operator, not a counterparty.** The prize is funded entirely by entrants' pooled fees; the platform takes only a **rake** and has **zero outcome position**. Settlement invariant: `sum(payouts) + rake = sum(entries)` — identical to the P2P model. Rake is taken **only when a prize is actually distributed**: if nobody clears, every entry is refunded and the platform earns nothing, so it never profits from player failure.

Implementation: `api/_lib/solo_challenge.py` (pool engine + geo-fence) and the `SoloPool` / `SoloEntry` / `MetricTarget` models in `api/_lib/schemas.py`; endpoints `POST /api/solo/pools`, `POST /api/solo/pools/enter`, `POST /api/solo/pools/settle`.

### 10.2 Supported games & qualifying standards

Standards are **skill-attributable, player-controlled metrics**, decoupled from match win/loss so a player is graded on the quality of their own play.

| Game | Metrics | Skill defense |
| --- | --- | --- |
| **Rocket League** (`rocketleague.psyonix`) | Aerial-hit accuracy %, match score, saves, goals | Zero built-in randomness / RNG; the outcome is 100% a byproduct of human physics execution and mechanical skill. |
| **Clash Royale** (`clashroyale.supercell`) | Crown-tower damage; elixir-efficiency thresholds (e.g. deal 4,000+ damage using <30 total elixir) | Bypasses the luck of card shuffles / bad matchups by ignoring win/loss and grading macro-efficiency a skilled player controls regardless of match outcome. |
| **Chess** (`chess.lichess`) | Engine accuracy % (e.g. maintain >82% per Stockfish over 20+ moves), blunder-free positional play | Shields players from asymmetric-matchmaking chance — even if paired with a master and beaten, you clear the challenge if you executed accurate, high-quality chess. |

### 10.3 Guardrails

- **Rigid GPS geo-fencing** of the 14 "Any Chance" states — **AZ, AR, CT, DE, FL, IN, LA, MD, MN, MT, SC, SD, TN, WY** — enforced *before* any entry fee is escrowed (`solo_challenge.assert_can_enter`), mirroring the client gate (§9.2).
- **Absolute ban on prop-betting metrics.** Standards must be skill-attributable performance bars; pure predictions (e.g. "the game will last under N minutes") are prohibited.
- **Telemetry is host-authoritative.** The standard is graded from the game API's finalized telemetry, never a self-report.
- **No house-banked variant.** The platform never offers a guaranteed/fixed prize it funds, and never sets a payout "line" against a player.

### 10.4 Why pooled, and not house-banked

The tempting "pay an entry, clear a bar, win a guaranteed fixed prize the platform pays" design is **rejected**, for two reasons the team should keep in mind whenever this feature is discussed:

1. **A guaranteed, platform-funded prize is house-banked.** It makes the platform win when the player fails and lose when the player clears — outcome risk on the platform's book, which contradicts the neutral-operator invariant in [§2](#2-why-peer-to-peer) and [§7.1](#71-wallet--escrow). Relabelling it an "indirect payout" does not change the economic substance.
2. **Removing chance is necessary but not sufficient.** The Predominant Factor Test addresses the *chance* element only. In the "Any Chance" states — and per the South Carolina signal in §9.2 — *consideration + a prize + a contingent payout* can constitute gambling **regardless of skill**. A house-banked solo wager is therefore *higher* risk than the pooled contest, not lower.

The pooled tournament above sidesteps (1) entirely (no platform outcome position) and is the strongest available answer to (2) (it is structurally a contest of skill among entrants, like DFS / Skillz / poker). It still requires gaming-counsel sign-off per state before real money, and stays **play-money only** until then.

---

## 11. Glossary

| Term | Definition |
| --- | --- |
| **Skill contract / contest** | An escrowed, peer-to-peer agreement to compete on a measurable objective for a pot. |
| **Lobby** | The feed of OPEN contests a player can join. |
| **Builder** | The surface for posting a custom contest within allowed dimensions. |
| **Pot** | The sum of all entrants' entries for a contest. |
| **Rake** | money match's fixed, disclosed fee taken off the pot. The only revenue; the platform takes no outcome position. |
| **Entry** | A single player's stake to join a contest. |
| **Window** | The time / qualifying-game budget within which a contest resolves. |
| **Qualifying game** | A host-platform game matching the contest's game, format, and match-type filters. |
| **Matchmaking / bracketing** | Skill-banded pairing of players — how fairness is created (replaces odds-setting). |
| **Settlement** | Host-authoritative reading of results that resolves the contest and pays the pot. |
| **GameAdapter** | The interface each title implements so matchmaking / escrow / settlement stay shared. |
| **Collusion** | Two accounts fixing a result to move value / dodge the rake — the core integrity risk of this model. |