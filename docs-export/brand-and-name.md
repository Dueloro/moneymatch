# Brand & Product Name Guide

How the product presents itself in words and identity. The visual system (colour,
type, components) lives in [`design-guidelines.md`](./design-guidelines.md); this
covers **name, voice, and messaging**.

---

## 1. Money Match vs Dueloro — the rule

**Money Match is the product. Dueloro is the developer (the company).** They are
not competing names; they name different things.

Inside the product we use **Money Match only**. There are exactly two exceptions
where **Dueloro** appears:

1. **Support / reaching out to us** — the entity a user contacts is **Dueloro**
   (e.g. "Dueloro Support", support email/handle).
2. **The marketing site** — the public site is **dueloro.com**; link to it by that
   name.

Everywhere else — the wordmark, sign-in, invite landing, in-app copy, contest
surfaces, notifications, receipts — it is **Money Match**. Never introduce
"Dueloro" into product copy outside those two cases, and never call the product
itself "Dueloro".

The mark is stable across both: a **lime triangle** (44px on sign-in / invite,
28px rounded-square lozenge in the shell).

> **Code note:** the in-app support thread currently reads **"MoneyMatch
> Support"**. Per rule (1) the support entity is Dueloro, so that label should
> become **"Dueloro Support"**. Not changed yet — flag if you want it updated.

---

## 2. Who we're talking to

Competitive gamers who already grind Chess, CS2, Dota, PUBG. They are
skill-proud, skeptical of anything that smells like a casino or a scam, and quick
to distrust fabricated numbers. The brand's job is to read as **a fair arena for
people who are actually good**, not a betting product.

## 3. The one-line positioning

> **Put your skill on the line.** Peer-to-peer skill wagering on the games you
> already play — you stake into a shared pot, play a real match, and the winner
> takes it minus a small, disclosed fee. We hold the pot. We never take a side.

Three claims are always safe and always on-message, because they are literally
true of the system:

1. **"We hold the pot. We never take a side."** (neutral operator — the trust and
   legal core.)
2. **"Results are verified by the game, not by you."** (host-API settlement, no
   screenshots, no self-report.)
3. **"You always see the fee before you stake."** (rake disclosed pre-commit.)

## 4. Voice

- **Confident, plain, unhyped.** Short sentences. Name the thing. The audience
  respects competence, not adjectives.
- **Trust over persuasion.** Lead with how it works (fair, verified, transparent),
  not with "win big". This is the moat over every screenshot-and-dispute rival.
- **Never imply the house roots for you to lose** — it doesn't, and saying
  otherwise would be both off-brand and legally wrong.

**Say / don't say:**

| Say | Don't say |
| --- | --- |
| stake, entry, pot, prize, contest, match | bet, gamble, wager against us |
| fee / rake (disclosed) | vig, odds, line, house edge |
| verified by the game | trust us, we checked |
| eligible U.S. states, 18+ | (never omit these on money surfaces) |

## 5. Copy mechanics (enforced in the app)

These are enforced at the render boundary (see `design-guidelines.md` §8) — match
them in marketing copy too so the two never diverge:

- **Sentence case** everywhere except the wordmark.
- **Zero em dashes** in rendered copy.
- **No `≈`.** An estimate says `est.` once, next to a properly-formatted number.
- **Money is always fully formatted** (`$18.00`), from integer cents.
- **Buttons name the outcome and keep the name through the flow** (`Join pool` →
  `Joining…` → `Joined the pool`).
- **Empty states end in a next action, not an apology.**

## 6. Compliance in messaging (non-negotiable)

- Persistent **18+** and **"cash play in eligible U.S. states only; free play
  everywhere"** on money-facing surfaces (mirror the app's onboarding gate).
- **Honest liveness only.** Show representative real entry tiers; never invent
  "128 online / $2,400 in pots" until a real stats endpoint exists. The app's
  ticker already hides when no one is queuing — hold marketing to the same bar.
- Link **Terms**, **Privacy**, **Responsible Gaming**, and **contact** wherever
  money is mentioned.

See [`legal/legal-compliance.md`](./legal/legal-compliance.md) for the underlying
posture and [`product/overview.md`](./product/overview.md) for the full product
definition.
