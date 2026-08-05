# UI Revamp — design plan

Baseline: the pre-revamp UI, audited screen by screen before any code changed.
That audit lived in `15-ui-inventory.md`, which was never committed and has since
been lost from disk; its findings survive as the diagnosis table in §1 below and
as the "the inventory found" notes in the component doc comments. The current UI
is described in [`17-ui-current-state.md`](./17-ui-current-state.md).

This doc only states what changed and why.

The goal is not "more design". It is **fewer, better-argued decisions, enforced
in code**. Every section below ends in a rule that a component encodes, so the
next screen can't drift.

---

## 1. The diagnosis, in one line each

| Tell | Root cause | Fix |
| --- | --- | --- |
| Nine cards saying the same sentence | Entry treated as a product instead of a parameter | One card per **bar**; entry is a control inside it |
| Explainer paragraph on every browse page | The cards don't communicate | Make the card self-evident, demote prose to a dismissible note |
| Lime everywhere | One accent doing five jobs | Split the jobs across a real semantic set |
| Flat void | `bg` and `panel` differ by ~1.5% luminance | A genuine surface ramp |
| Oceans of dead space at 1920px | No layout above 1180px | 12-col grid, persistent right rail |
| Mono uppercase micro-labels everywhere | One label style used at every rank | Three heading levels; mono reserved for money labels |
| Nine loud CTAs | Every card ends in a solid lime button | Three cards, and primary is no longer lime |
| Four radii, three heading styles, two loaders | No enforced primitives | One `Card`, one `SectionHeader`, one loader |
| Invisible focus, hidden scrollbars | Never specified | Global `:focus-visible`, real thin scrollbars |
| **Inter never loaded** | No `@font-face` or font link exists | Load it |
| **Fabricated "3 of 4 joined"** | `filledSpots()` hashes the card key | Flagged, see §8 |

---

## 2. Colour: what replaced each of lime's five jobs

Lime currently means money, primary action, live, win, and selected. After:

| Old lime job | Now | Token |
| --- | --- | --- |
| Money, payouts, balance | **still lime** | `--money #c6f440` |
| Primary action | **paper** (near-white fill, ink text) | `--action #f2f5ef` |
| Live / in progress / online | **cyan** | `--live #4fd1e0` |
| Win / positive outcome | **lime** (it is money) | `--money` |
| Selected | **structure**: raised surface + strong border, no hue | `--panel-raised` + `--line-strong` |

**Lime now means exactly one thing: money.** If a number is not currency, it is
not lime.

Why paper for the primary action rather than a second hue: it is the highest
contrast available on this ground, it can never be confused with a dollar figure,
and it keeps the palette at one warm accent instead of two competing ones. The
codebase already had this exact treatment sitting unused as the `secondary`
button variant.

Why cyan for live: it is the only cool hue in the system, so "this is happening
now" reads as a different *kind* of information at a glance rather than a
different *value*. Used only in small doses (dots, one-word labels).

### The full token set

```
Surfaces (neutral ink, no green cast)
  --bg            #0b0c0f   page
  --panel         #111318   card surface
  --panel-raised  #171a20   input, hover, chip, selected
  --overlay       #1d212a   dialog, menu
  --hairline      #23272f   default 1px line
  --line-strong   #333945   hover line, overlay edge

Text
  --text            #eef0f4   primary
  --text-secondary  #9aa2b1   subline          (7.2:1 on panel, AAA)
  --text-tertiary   #7c8593   meta, disabled   (5.0:1 on panel, AA)

Semantic
  --money  #c6f440   currency, gains, balance
  --action #f2f5ef   primary action fill
  --live   #4fd1e0   in progress, online, searching
  --loss   #ff5f48   loss, error, destructive
  --warn   #f5b93c   pending, caution
  --focus  #a8c7ff   focus ring only, never decorative
```

The page ground moves from `#080a07` (green-cast near-black) to `#0b0c0f`
(neutral ink). This is the change that lets lime read as an accent instead of as
the room's ambient colour, and it opens a real gap between page, card, and raised
surfaces.

**Game accents keep existing but leave the browse cards.** Four warm hues that
sit within 40° of each other carry no information on a page already filtered to
one game. They stay in the game switcher and in chat invite cards, which are the
two places more than one game can appear at once.

---

## 3. Type

**Load Inter.** It was always the intended face and was never delivered. It is
the right genre for a numbers-dense money product: large x-height, true tabular
figures, drawn for screen UI. Adding it is a two-line `<link>`, no dependency, no
build change. Tabular figures are turned on globally for money.

One scale, replacing Tailwind's defaults so existing markup snaps to it:

| Step | Size / line | Use |
| --- | --- | --- |
| `text-micro` | 11 / 16, +0.02em | Badges, counts, the one mono label |
| `text-xs` | 12 / 18 | Sublines, meta, timestamps |
| `text-sm` | 14 / 22 | **Body default** |
| `text-base` | 16 / 24 | Lead paragraphs, card titles |
| `text-lg` | 18 / 24, ‑0.006em | Card headline, dialog title |
| `text-xl` | 20 / 26, ‑0.011em | Section heading |
| `text-2xl` | 24 / 30, ‑0.018em | Page title |
| `text-3xl` | 30 / 36, ‑0.022em | Hero number (the bar target, balance) |

The one-offs die: `text-[15px]` → `text-sm`, `text-[13px]` → `text-xs`,
`text-[11px]`/`text-[10px]` → `text-micro`.

**Three heading levels, one component.** `SectionHeader` renders `page` (24px
semibold), `section` (20px semibold), or `sub` (14px semibold, secondary). The
mono uppercase treatment is cut from every heading and survives in exactly one
job: the tiny label above a money figure (`Entry`, `Pot`, `Balance`), where its
technical register is doing work.

---

## 4. Space and shape

- **Spacing:** 4 / 8 / 12 / 16 / 24 / 32 / 48. No half-steps. The `py-2.5`,
  `px-3.5`, `gap-3.5` scattered through the current code all round to the scale.
- **Radius, three values with a rule:** `--radius-card 12px` for anything that
  sits on the page, `--radius-inset 8px` for anything nested inside a card,
  `--radius-pill` for controls. That is a hierarchy, not four competing values.
- **Border:** every surface on the page carries `1px --hairline`. No borderless
  panels. Overlays get `1px --line-strong`.
- **Elevation:** exactly one shadow token, used only by overlays (dialog, menu,
  toast). Cards never cast shadows; they separate by border and surface value.

---

## 5. Layout

**Grid.** 12 columns, 24px gutters, container caps at 1440px (from 1180px). One
rule for column width, replacing the eight arbitrary ones:

- **Browse pages** (Pools, Tournament, Head-to-head): content spans 8 columns, a
  persistent **320px right rail** takes the rest at ≥1280px.
- **Reading pages** (Activity, Wallet, Profile): content caps at 640px, and the
  same rail fills the remaining width so the page never strands.
- **Below 1280px:** the rail does not render. (The plan first called for it to
  collapse into a horizontal strip; in build that turned into a very tall block
  on tablet, so it hides instead and the sidebar footer carries the balance.)

**The right rail is what fills the void, with real information:** your balance,
what you have in play right now, and who is queuing. All from hooks that already
exist (`useWallet`, `usePoolStatus`, `useTournamentStatus`, `useQueueStatus`,
`useWaiting`, `useActivity`). No new endpoints.

**Navigation drops from six items to four.** Pools, Tournament, and Head-to-head
are three modes of one act, so they collapse into **Play**, with a mode switcher
at the top of that surface. Routes are unchanged and every page stays one tap
away. The mobile bar goes from six ~62px tabs to four ~94px tabs, clearing the
44px touch-target floor with room to spare. The sidebar gets its reclaimed space
back as a balance footer.

### Wireframe: Solo Pools, desktop ≥1280px

```
┌────────────┬──────────────────────────────────────────┬──────────────────┐
│ Money Match│  Play                                    │  BALANCE         │
│            │  ┌──────────────────────────────────┐    │  $1,008.00       │
│ ▸ Play     │  │ Pools │ Tournament │ Head-to-head│    │  $10.00 in play  │
│   Activity │  └──────────────────────────────────┘    │                  │
│   Social   │  ⌁ Counter Strike  ⌁ PUBG   [How it works]│  IN PLAY         │
│   Wallet   │                                          │  ┌─────────────┐ │
│            │  ┌────────────┐┌────────────┐┌─────────┐ │  │ Medium pool │ │
│            │  │ Easy       ││ Medium     ││ Hard    │ │  │ bar 1.75    │ │
│            │  │            ││            ││         │ │  │ ● live      │ │
│            │  │ Clear      ││ Clear      ││ Clear   │ │  └─────────────┘ │
│            │  │ 1.65       ││ 1.80       ││ 2.00    │ │                  │
│            │  │ ▬▬▬▬●──┤   ││ ▬▬▬●────┤  ││ ▬●───┤  │ │  QUEUE           │
│            │  │ you 1.42   ││ you 1.42   ││you 1.42 │ │  kvem_  K/D $10  │
│            │  │            ││            ││         │ │  s1mple K/D $25  │
│            │  │ $5 [$10] $25││$5 [$10] $25││$5[$10]$25│ │                  │
│            │  │ Win $29.00 ││ Win $56.25 ││Win $225 │ │                  │
│            │  │ [Join pool]││ [Join pool]││[Join]   │ │                  │
│ ─────────  │  └────────────┘└────────────┘└─────────┘ │                  │
│ $1,008.00  │                                          │                  │
└────────────┴──────────────────────────────────────────┴──────────────────┘
```

Nine cards become three. The sentence "Clears ≈ 31% of the time" is replaced by
the bar, which shows the same fact spatially. Entry is a segmented control, and
the payout under it updates as you change it.

### Wireframe: Solo Pools, mobile 375px

```
┌───────────────────────────┐
│ Money Match          ◉ ● │  top bar: logo, bell, avatar
├───────────────────────────┤
│ Pools │ Tourn. │ H2H      │  mode switcher, scrolls
│ ⌁ Counter Strike  ⌁ PUBG  │  game switcher, scrolls
├───────────────────────────┤
│ Balance $1,008.00  ·  $10 │  compact rail strip
│ in play                   │
├───────────────────────────┤
│ ┌───────────────────────┐ │
│ │ Easy                  │ │
│ │ Clear 1.65            │ │
│ │ ▬▬▬▬▬▬●─────┤         │ │
│ │ your avg 1.42         │ │
│ │ $5  [$10]  $25        │ │
│ │ Win $29.00            │ │
│ │ [     Join pool     ] │ │
│ └───────────────────────┘ │
│ ┌───────────────────────┐ │
│ │ Medium …              │ │
├───────────────────────────┤
│  Play  Activity Social 💰 │  4 tabs, 94px each
└───────────────────────────┘
```

### Wireframe: Wallet, desktop

```
┌────────────┬────────────────────────────────┬──────────────────┐
│ nav        │  Wallet                        │  rail            │
│            │  ┌──────────────────────────┐  │                  │
│            │  │ AVAILABLE                │  │  IN PLAY         │
│            │  │ $1,008.00        ← 30px  │  │  …               │
│            │  │ $10.00 in play · +$8 all │  │                  │
│            │  │ time                     │  │  QUEUE           │
│            │  └──────────────────────────┘  │  …               │
│            │  Add funds   $10 $25 $50 $100  │                  │
│            │  Cash out    $10 $25           │                  │
│            │  Recent                        │                  │
│            │  ● Winnings      2h    +$18.00 │                  │
│            │  ● Entry held    2h    −$10.00 │                  │
└────────────┴────────────────────────────────┴──────────────────┘
```

The three-cell StatBar becomes one hero figure with its context as a subline.
Available balance is the number you came for; escrow and lifetime are supporting
detail, not equals.

---

## 6. The signature

**The clear bar.** A horizontal track showing your baseline, the target you have
to beat, and the gap between them, with the gap shaded.

```
      your avg 1.42          target 1.80
 ├──────────●───────────────────┤
            ╰─── you need +0.38 ─╯
```

It is the product's actual idea rendered as an object. It replaces a sentence
("Clears ≈ 16% of the time") with a picture, it encodes difficulty spatially
(hard = the target sits further right), and it is the same component in four
places: the contest card, the formed-room banner, the Activity live line, and the
rail's in-play card. Nothing else in the UI is allowed to be this loud.

Everything around it stays quiet: paper buttons, one accent for money, no
gradients, no glow, no decorative chrome.

---

## 7. Copy rules, enforced

- Zero em dashes in rendered copy. Server strings that contain them (game display
  names, forecast labels) are normalised at the render boundary by `dashless()`.
- Sentence case everywhere except the wordmark.
- Buttons name the outcome and keep the name through the flow: `Join pool` →
  `Joining…` → toast `Joined the pool`.
- `≈` is gone. An estimate says `est.` once, next to a properly-formatted number.
- Empty states end in a button, not an apology.

---

## 8. What this plan deliberately does not fix

**`filledSpots()` invents the "3 of 4 joined" figure** by hashing the card key
into the range [half full, one short of full]. It is fabricated social proof on a
real-money product, and it is the one thing in this codebase I would escalate
rather than restyle. The revamp keeps rendering it (removing data is outside a UI
brief) but stops giving it a progress bar and prominence it hasn't earned. It
needs a product decision: show a real count, or show nothing.

Admin (`/admin/*`) is untouched by design.

---

## 9. Critique of this plan, before building it

*Would a generic model hand back the same thing?* For three of these decisions,
yes. Naming them honestly:

**Neutral ink ramp plus a near-white primary button is the default answer.** It
is what every model produces when told "dark plus one accent is a cliché", and it
is what Vercel and Linear already look like. I am keeping it anyway, because the
constraint "lime must mean money and nothing else" leaves no high-contrast
primary that doesn't introduce a second competing hue, and inventing one to look
original would be worse design. What I will not do is pretend it's novel: **the
novelty budget is spent entirely on the clear bar and on the information
architecture** (one card per bar, the rail, six nav items down to four), which is
where a redesign actually changes how the product feels to use. The palette's job
is to get out of the way.

**Cyan for "live" is the weakest call here.** Lime plus cyan on near-black is
recognisably the crypto-dashboard palette, and that is a real risk. I considered
amber (collides with the warm game accents, and sits close enough to lime that a
6px dot could be misread) and "no colour at all, just motion" (loses the
at-a-glance distinction that presence dots need). Cyan wins on unambiguity, so it
stays, but **constrained**: dots, 1px rules, and single-word labels only. Never a
fill, never a button, never a run of text. If it starts spreading, it was the
wrong choice.

**A right rail is the obvious way to fill 1920px.** What keeps it from being
filler is its contents: live contests rendered with the same bar component as the
cards, and the real queue, not a "stats" widget. If the rail ever needs invented
content to look full, the layout is wrong and it should collapse.

**Revised as a result of this critique:** cyan's usage is now explicitly bounded
(above); the plan no longer claims the palette as a differentiator; and the bar is
promoted from "a nice card detail" to the component that must appear in all four
in-play surfaces, so it reads as the product's object rather than a chart.
