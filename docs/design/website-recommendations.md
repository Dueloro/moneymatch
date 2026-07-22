# Marketing website recommendations (dueloro.vercel.app)

**Context.** These are recommendations for the public marketing site at
`dueloro.vercel.app`, written while aligning the beta app to the Dueloro brand.
The app now shares the site's identity (acid-lime accent, triangle mark,
near-black + glow, highlight-marker headlines, live VS card, mono micro-labels),
so the two finally read as one product. The notes below are about the *site*.

The site was reviewed by rendering it headless (it is a client-rendered SPA).
Some observations are therefore about how it renders to a first paint / crawler,
not just how it looks after full hydration + scroll.

---

## What's strong — keep it

- **Brand voice and identity.** "Put your skill on the line," the acid-lime on
  near-black, the highlight-marker on key words, the live VS card, the contest
  ticker, and the "Open beta · Season 01" framing are all excellent and exactly
  right for the audience (competitive gamers). This is the north star the app
  was just brought in line with.
- **The hero VS card and the contest marquee.** These sell the product in one
  glance. Do not lose them.
- **"We hold the pot. We never take a side."** The neutral-operator message is
  the legal and trust core and it's stated well.

---

## Recommendations

### 1. Wire the funnel to the beta (highest priority)
Every "Join the beta" / "Get early access" CTA should deep-link straight to the
app's `/signin` (or `/`). The app landing now redirects signed-in users to Play
and gives cold visitors context, so a direct hand-off is clean. Make sure the
button is a real link to the app origin, not an in-page anchor.

### 2. Don't hide core content behind scroll animations
On first paint, large mid-page regions render dark/empty until scroll-triggered
reveals fire. That hurts three audiences at once: crawlers/social unfurlers,
users on slow connections, and anyone with reduced-motion. Ensure all core copy
is present in the DOM at load and only *animate* it in — never gate its existence
on an IntersectionObserver. Add a `prefers-reduced-motion` path.

### 3. Show the real product, not just a mockup
The hero card is great; add 2–3 actual app screenshots now that the app looks the
part (the Play markets screen, the matched VS slip, a settled Activity row with a
green `+$18.00`). "Show, don't tell" converts this audience.

### 4. Share one design-token source with the app
The app now encodes the brand as CSS variables (`--green: #c6f440`, near-black
base, glow, `.mark`, `.label-mono`). Extract these into a shared package or a
copied token file so the site and app never drift on hex values, radii, or the
marker/label treatments.

### 5. Honest liveness, not fabricated counters
The app's ticker is fed by *real* players in queue and hides when empty (the
"no seeded/bot content" rule). The site's marquee can show representative entry
tiers (real offered stakes), but avoid inventing "128 online / $2,400 in pots"
until there's a real stats endpoint — a wagering audience is quick to distrust
numbers that feel fake. When real aggregates exist, surface them.

### 6. Trust, legal, and responsible-gaming footer
For a real-money skill product this is table stakes and reduces bounce/anxiety:
- Persistent **18+** and **"cash play in eligible U.S. states only; free play
  everywhere"** (mirror the app's onboarding + eligibility banner).
- Links to **Terms**, **Privacy**, **Responsible Gaming**, and a **contact**.
- A short **FAQ** (the nav already promises one): "Is this gambling?", "How do
  you make money?", "Which states?", "How are results verified?", "Can I get
  cheated?". These are the exact objections this audience raises.

### 7. Metadata, OG, and performance
- Real OG/Twitter image (the VS card renders beautifully as a share card),
  description, canonical URL, and favicon (the triangle mark).
- As an SPA, add prerendering/SSG for the landing route so the first paint and
  the social unfurl don't depend on JS. This also fixes #2 for crawlers.

### 8. Mobile pass
Confirm the hero VS card, marquee, and nav collapse cleanly on a phone — that's
where most of this audience arrives from a shared link. (The app's shell was
just made fully responsive; hold the site to the same bar.)

### 9. One clear primary CTA per viewport
There are several entry points (nav "Join the beta", hero, footer "Get early
access"). Keep them, but make the label consistent ("Enter the beta") and ensure
each viewport has exactly one visually dominant CTA so the path is obvious.

---

## Nice-to-have

- A tiny **"how settlement works"** animation (host API → result → payout) — the
  auto-verification is the trust differentiator and is hard to convey in text.
- A **season/leaderboard teaser** to lean into the "Season 01" framing and hint
  at retention loops.
- **Discord/community link** in the footer — this audience organizes there, and
  it's cheap social proof + a support channel during beta.
