# MoneyMatch — Design Guidelines

**What this is.** The design system the product's UI follows today, written so a
new engineer or agent can build a new screen that looks like it belongs without
seeing the app first. It is descriptive of the current build (post-revamp) and
prescriptive for new work: when in doubt, match what is here.

**The one rule that generates most of the others:** *fewer, better-argued
decisions, enforced in code.* Every primitive below is a real component; new
screens compose those primitives rather than inventing spacing, colour, or type.

The consumer app is dark-theme only. The `/admin` surface is deliberately outside
this system (see §9).

---

## 1. Colour

Defined as CSS custom properties in `apps/web/src/styles/index.css` and mapped
into Tailwind, so class names like `bg-panel` and `text-green` resolve to tokens.
Never hard-code a hex in a component.

### 1.1 Surfaces — a real luminance ramp

Each step is visibly lighter than the last; that ramp is what lets a card read as
sitting *on* the page rather than floating.

| Token | Hex | Role |
| --- | --- | --- |
| `bg` | `#0b0c0f` | The page. Neutral ink, faintly blue — not black, not green |
| `panel` | `#111318` | Card surface |
| `panel-raised` | `#171a20` | Inputs, hover, chips, the selected segment |
| `overlay` | `#1d212a` | Dialogs and menus (float above the page) |
| `hairline` | `#23272f` | Default 1px border on every card |
| `line-strong` | `#333945` | Hover/selected borders, overlay edges |

### 1.2 Text — all contrast-checked against `panel`

| Token | Hex | Contrast | Use |
| --- | --- | --- | --- |
| `text` | `#eef0f4` | 16.3:1 | Primary (off-white, easier than pure white) |
| `text-secondary` | `#9aa2b1` | 7.2:1 AAA | Sublines, labels, inactive |
| `text-tertiary` | `#7c8593` | 5.0:1 AA | Meta, timestamps, disabled, counts |

### 1.3 Semantics — one job per colour (the most important rule)

| Token | Hex | Reads as | Its only job |
| --- | --- | --- | --- |
| `green` | `#c6f440` | Acid lime | **Money.** Currency, balances, payouts, winnings, ROI. If a number is not currency, it is not lime |
| `action` | `#f2f5ef` | Near-white | **The primary action.** Filled buttons, send button, your own chat bubble, checked boxes, unread badges |
| `live` | `#4fd1e0` | Cyan (the only cool hue) | **Happening now.** Presence/searching dots, in-progress states, the queue, "Linked" |
| `red` | `#ff5f48` | Orange-red | Loss, error, destructive, the platform fee |
| `warn` | `#f5b93c` | Amber | Pending/caution. Defined but almost unused — the free slot for a future "pending" semantic |
| `focus` | `#a8c7ff` | Pale blue | The focus ring, and nothing else |

Two hard constraints when extending the palette:

1. **Selection is not a colour.** A selected chip/tab/segment gets a raised
   surface + a `line-strong` border, no hue. That is what lets an entry picker
   sit two lines above a lime payout without competing.
2. **One meaning per colour.** The revamp's whole gain was that lime stopped
   meaning five things. Add a new colour only if it arrives with a single job.

**Cyan (`live`) is deliberately underused** — dots, one-word labels, and the 25%
wash in the clear bar only. It never fills a shape or runs across a sentence. It
is the intended candidate if a second main colour is ever promoted, because its
meaning ("happening now") is already established.

**Game accents** (`#f0883e` CS2 orange, `#e8a13a` PUBG amber, `#e6c65c` chess
gold, `#e15b4c` Dota brick) appear in only two places: the icon of the
**selected** game tab, and chat invite cards — the two spots where more than one
game can appear at once. They are not used on browse cards.

**Chat avatar accents** are five pastels picked by hashing the person's name
(same person, same colour). They appear nowhere outside chat.

---

## 2. Type

**Inter**, loaded from Google Fonts at 400/500/600/700 with `display=swap`.
`font-variant-numeric: tabular-nums` is on globally so money never jitters.

One scale (overrides Tailwind defaults). There are no arbitrary sizes.

| Class | Size / line height | Use |
| --- | --- | --- |
| `text-micro` | 11 / 16, +0.02em | Badges, counts, the money caption |
| `text-xs` | 12 / 18 | Sublines, meta, timestamps |
| `text-sm` | 14 / 22 | **Body default** |
| `text-base` | 16 / 24 | Lead paragraphs |
| `text-lg` | 18 / 24 | Card headlines, dialog titles |
| `text-xl` | 20 / 26 | Section headings |
| `text-2xl` | 24 / 30 | Page titles |
| `text-3xl` | 30 / 36 | Hero numbers: balance, the bar target |

Headings tighten letter-spacing as they grow (−0.006em at 18px → −0.022em at
30px). **One mono label survives**, `.label-money`: 11px, uppercase, 0.08em
tracking, tertiary grey — used *only* as the caption directly above a currency
figure (`ENTRY`, `POT`, `BALANCE`, `EST. WIN`). Its scarcity is what makes it
read as "this is a number."

---

## 3. Shape, depth, motion

- **Radii — three values with a rule.** `card` (12px) for anything sitting on the
  page; `inset` (8px) for anything nested inside a card; `pill` (999px) for
  controls; `rounded-full` for circles. Nothing else.
- **Border.** Every on-page surface carries 1px `hairline`. There are no
  borderless panels. Overlays get 1px `line-strong`.
- **Elevation.** Exactly one shadow token, used only by dialogs, menus, toasts.
  Cards never cast shadows — they separate by surface value and border.
- **Motion.** Four animations only, all disabled under `prefers-reduced-motion`
  (which also clamps transitions to 0.01ms): the ticker marquee, the 0.28s rise
  on a matched card, `animate-pulse` on live dots/skeletons, and a 260ms FLIP
  glide when game pills reorder. The balance counts up rather than snapping.
- **Focus.** One global rule: `:focus-visible` draws a 2px `focus` ring with 2px
  offset on every interactive element. Mouse clicks don't ring; every keyboard
  path does.
- **Scrollbars** are thin and visible (10px track, `hairline` thumb that lightens
  on hover). Only the ticker hides its gutter.

---

## 4. Component primitives

New screens compose these. If a screen needs something not here, add it as a
primitive rather than a one-off.

- **`Card`** — the one surface primitive: 12px radius, 1px hairline, `panel`
  fill, no shadow. Tones: `default`, `raised`, `overlay` (stronger border +
  shadow, for dialogs). `interactive` adds the hover border.
- **`PillButton`** — the only button. Fully rounded, semibold. Variants:
  `primary` (solid near-white, dark ink — the loudest thing on a screen),
  `secondary` (`panel-raised` + hairline), `outline` (transparent + hairline),
  `text` (grey label, white on hover), `danger` (red border + red text). Sizes
  `sm` / `md` / `lg`. Disabled drops to 40% opacity. Call sites never override
  padding.
- **`SectionHeader`** — the only heading component. Levels `page` (24px, `h1`),
  `section` (20px, `h2`), `sub` (14px, `h3`). Optional grey `hint` and a
  right-aligned `action` slot.
- **`Segmented`** — the one "pick one of a few" control (mode switcher, entry
  amount, sub-tabs). Recessed `panel` track + hairline, 4px padding; the selected
  option is a `panel-raised` pill with an inset `line-strong` ring. Renders as a
  real tablist.
- **`WagerCard`** — the joinable contest, and the most important layout in the
  product (§6). One card per **bar**, never one per stake.
- **`ClearBar`** — the signature object (§7).
- **`CardGrid`** — caps columns by card count (1 → 384px single column, 2 → 768px
  two-col, 3+ → responsive 1/2/3) so a single contest never sits alone in a wide
  grid looking like an error.
- **`ExpandableCard`** / **`ListRow`** — the expandable and flat row primitives.
- **`FilterBar`** — pill toggle with a hamburger, "Filters", and a paper
  active-count badge; opens a `Card` of chip rows.
- **`GameTabs`** — the game switcher; selected pill gets a `panel-raised` fill, a
  strong border, and **its icon in the game's accent**.
- **`EmptyState`** — a dashed hairline box (title, grey line, usually a button).
  **`ErrorState`** is the same with a red-tinted dashed border + "Try again".
- **`Skeleton`** / **`SkeletonList`** — `panel-raised` pulses at 8px radius. The
  only loading treatment in the app.
- **Form controls** (`TextInput`, `TextArea`, `Select`, `Checkbox`, `RadioRow`)
  share one treatment: pill-shaped, `panel-raised` fill, hairline that lightens
  on hover. No native browser control is ever visible.

---

## 5. Layout & shell

`AppShell` wraps every signed-in route. Sign-in, the invite landing, and admin
sit outside it.

| Width | Nav | Right rail | Balance lives | Contest grid |
| --- | --- | --- | --- | --- |
| < 768 | Bottom bar, 4 tabs | None | Top-bar chip | 1 column |
| 768–1023 | Sidebar 224px | None | Sidebar footer | 2 columns |
| 1024–1279 | Sidebar 224px | None | Sidebar footer | 3 columns |
| 1280+ | Sidebar 224px | 320px, right | Sidebar footer + rail | 3 columns |

- **Navigation is four items:** Play, Activity, Social, Wallet (+ role-gated
  Admin). Pools / Tournament / Head-to-head are three *modes of one act* and live
  under Play with a mode switcher; Play stays lit on all three routes.
- **The right rail** (≥1280px) is filled with real information, never invented
  content: the balance card, what's in play now, and who's queuing — all from
  existing hooks. If it ever needs invented content to look full, the layout is
  wrong and it should collapse.
- **The ticker** renders only when real players are queuing, and hides when
  empty. No seeded/bot liveness.
- **Spacing scale:** 4 / 8 / 12 / 16 / 24 / 32 / 48. No half-steps.
- **Container** caps at 1440px with 32px side padding.

---

## 6. The `WagerCard`, top to bottom

The card is self-evident by design, so browse pages don't need an explainer
paragraph (the "How it works" prose lives in a dismissible disclosure instead).

1. Metric / field size in 12px grey (left) + optional `panel-raised` tag pill
   (right): difficulty, "top 3 paid", "BLITZ".
2. Title at 18px semibold.
3. **The headline number** at 30px semibold (e.g. `1.80`) with "to clear" beside
   it. (Tournaments and 1v1 have no bar, so they omit this.)
4. **The clear-rate meter:** a 6px track with a grey fill proportional to how
   often you clear that bar, over "16% of your recent matches clear it".
5. `ENTRY` mono caption, then a **segmented control of dollar amounts** (default
   middle preset).
6. `EST. WIN` over the payout at 18px **in lime**, with fill count ("3 of 4 in")
   or "1v1" on the right.
7. A full-width `lg` primary button naming the outcome: "Join pool", "Join
   tournament", "Find match".

Changing the entry updates the payout **in place**. Entry is a parameter, not a
product — this is why nine near-identical cards collapsed to three.

---

## 7. The signature: the clear bar

The product's one loud element, and the thing a stranger should remember. A
horizontal track showing **your number** against **the number to beat**, gap
shaded: a full-height white tick for the target, a filled bar for ground covered,
the remaining distance washed in cyan at 25%. Underneath, two 12px lines:
"your avg **1.42**" and either "need +0.38" (grey) or "clear" (lime). The target
sits at ~78% of the track so an overshoot reads as an overshoot.

It appears in exactly four places, always meaning the same thing: the
formed-room banner (Solo pools), the standings/in-play card, the rail's in-play
card, and the Activity live line. On browse cards — where the server quotes a bar
and a clear rate but not your baseline — the card shows the **clear-rate meter**
instead rather than inventing the "you" end of the bar. Nothing else in the UI is
allowed to be this loud; everything around it stays quiet.

---

## 8. Copy rules (enforced at the render boundary)

- **Zero em dashes** in rendered copy. Server strings containing them (game
  display names, forecast labels) are normalised by `dashless()` at render.
- **Sentence case** everywhere except the "Money Match" wordmark.
- **Buttons name the outcome and keep the name through the flow:** `Join pool` →
  `Joining…` → toast `Joined the pool`.
- **`≈` is gone.** An estimate says `est.` once, next to a properly-formatted
  number.
- **Money is always formatted from integer cents**, never a raw float.
- **The rake is always visible pre-commit** ("winner takes $18.00 · $2.00
  platform fee").
- **Empty states end in a button, not an apology.**

---

## 9. Admin is intentionally outside the system

`/admin/*` is a dense internal tool: white background, black text, 13px
monospace, bordered tables, square buttons, green `#080` for OK and red `#b00`
for anything wrong. It should keep looking like one. Do not apply the consumer
design system to it.

---

## 10. One honest open issue

`filledSpots()` in `apps/web/src/lib/spots.ts` invents the "3 of 4 in" figure on
every contest card by hashing the card key. It is not a live count. On a
real-money product that is fabricated social proof and needs a product decision —
show a real count, or show nothing — before any further visual work makes it more
prominent.
