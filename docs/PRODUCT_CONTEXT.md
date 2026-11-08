# Money Match — Product Context for Coding Agents

> **Source of truth.** Derived from the founders' current application drafts (Speedrun + YC, Nov 2026).
> Read this before making product, copy, or architecture decisions. If code or other docs disagree
> with this file, flag it. Don't silently pick one.

---

## 1. What we are building

**One sentence:** Skill-based wagering on the competitive video games you already play, automatically settled by the game's API.

**Short form (≤50 chars):** Skill-based wagering on competitive video games

**The problem.** Gamers already play each other for money. Today that means either:
- trusting a stranger in a Discord server to hold the pot (many players have been stiffed), or
- using platforms like Players' Lounge, where winners upload screenshots, sometimes stream the match, and wait for a human to approve the result.

**Our answer: remove the trust problem.**
1. Player picks a stake.
2. Player is matched with someone **in their skill band**.
3. They play on the **real game** (chess on Lichess today).
4. The result settles from the **game's official API in under a minute**.

No screenshots, no reviewers, no waiting.

**Core insight:** Finding a match is the easy part. Trusting the result is the hard part. Settling from the game's API is what lets this grow beyond one community.

---

## 2. Naming

| Thing | Name |
|---|---|
| Product | **Money Match** |
| Legal entity / company | **Dueloro, Inc.** (Delaware C corp) |

Use "Money Match" in all product UI and copy. "Dueloro" is only for legal/company contexts.

---

## 3. Current state (as of Nov 2026)

| Item | Status |
|---|---|
| Free play | **Live publicly on chess (Lichess) since Oct 20, 2026** |
| Usage since launch | ~50 players, ~125 matches |
| Real-money waitlist | 500 signups |
| Paying users | **None.** Real money is OFF. |
| Game developer partners | Launch-partner conversations with 3 developers |
| AI in the product | **None.** No AI models run in the product. (We use Claude Code and Codex to write code.) |

**Real money stays off until payments, identity verification, and geolocation are in place.** Do not build or ship anything that enables real-money flows without explicit instruction.

---

## 4. Roadmap (in order)

1. **Launch game partner** (a studio/developer)
2. **Payment processor**
3. **Identity (KYC) and geolocation providers**
4. **Real-money play for an invite-only group in eligible states**
5. Full-scale real-money launch in eligible states
6. Additional titles that have **official results APIs**

Longer term: the same settlement system can work for anything with a trusted, measurable result (e.g. fitness challenges settled from wearable data, fantasy sports). **Games are where we start.** Don't build for these yet, but don't hard-code assumptions that make them impossible.

---

## 5. Tech stack

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript |
| Backend | Python, FastAPI |
| Database | Postgres, with an **append-only ledger**; money stored as **integer cents** |
| Settlement | Separate **settlement worker** that polls game APIs and settles matches |
| Auth | Supabase Auth |
| Hosting | Render (backend) + Vercel (frontend) |
| Analytics / errors / email | PostHog / Sentry / Resend |
| AI coding tools | Claude Code, Codex |

Don't rebuild metrics, error tracking, or email in-app. PostHog, Sentry, and Resend already cover them.

---

## 6. Non-negotiable invariants

These are what make the product trustworthy and legally defensible. **Never break them.** Any change touching money, matches, or settlement must keep all of them.

1. **`sum(payouts) + fee = sum(entries)`** is enforced on **every** settlement.
2. **The server owns every number.** Clients never report results, amounts, or outcomes. The client never says "I won."
3. **Results come from the game's official API.** No screenshots, no self-reporting, no manual review.
4. **Fee is taken only when a pot pays out.** Refunds and cancellations take **no fee**.
5. **Money is integer cents in an append-only ledger.** No floats, no in-place updates or deletes of ledger rows.
6. **The platform never plays against users.** We earn the same whoever wins.

---

## 7. Game adapter architecture

Every game plugs in through **one adapter interface**:

- **link account**
- **fetch profile**
- **create match**
- **poll results**

Matchmaking, escrow, the fee, settlement, and the UI are written against this interface. **Adding a title means writing one adapter, not rebuilding matchmaking or settlement.**

Rules for agents:
- Keep game-specific logic **inside its adapter**. Don't add game-specific branches to core matchmaking, ledger, or settlement code.
- A new game is only a candidate if it has an **official results API**. Never add screenshot or OCR verification.
- Chess (Lichess) is the first and hero title. It's the first one, not the only one. Polish chess end-to-end before adding breadth.

---

## 8. Matchmaking

- Players are matched **within a skill band** (Elo-based), **not** on an open challenge board.
- Why: open challenge boards let experienced players pick off beginners. New players shouldn't be someone else's income.

---

## 9. Business model

- **Fixed 10% fee** on each pot when it pays out.
- **No fee** on refunds or cancellations.
- Same model as Skillz and Triumph: skill contests, a neutral operator, a fixed fee.
- Modeled revenue: ~$15–25 per paying player per month (modeled match frequency in PC titles; not validated).

---

## 10. Legal posture (what the product must respect)

- Money Match runs **skill contests, not gambling.** Players compete against each other, results come from the game itself, and we take a fixed fee without ever taking a side.
- Cash play is legal in **about 37 U.S. states.** We **geofence** the rest.
- **Identity is verified before real money goes live.**
- Free play can be available everywhere. Never imply cash play is available in an ineligible state.

---

## 11. Competitive context (why the product decisions matter)

| Competitor | What they do | Where we differ |
|---|---|---|
| **Skillz, Triumph** | Skill wagering in simple, in-house mobile games | We bring it to real competitive games people already play |
| **Players' Lounge** (YC W18) | P2P wagering on PC/console games | They use screenshots + human review and an open challenge board. We settle from the API and match by skill band. |
| **Discord wager servers** | A stranger holds the pot | No protection at all. We hold the pot and settle automatically. |

---

## 12. Product copy and tone

The audience is competitive players who distrust anything shady. They have been burned by Discord servers and frustrated by screenshot review.

**Messages that are always on-message:**
- "No screenshots, no reviewers, no waiting."
- "Matched with someone at your skill level."
- "Settles from the game's API in under a minute."
- "We never play against you." / "We earn the same whoever wins."

**Rules:**
- Plain, confident, short sentences. Name the thing.
- **Show real numbers or none.** Never invent player counts, active matches, or pot sizes in UI or copy.
- Never say anything like "win big" or "guaranteed winnings," or imply the platform loses when a player wins.
- Always show the fee clearly before a player commits a stake.