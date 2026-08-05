# UI Current State — what every screen looks like after the revamp

**Status:** describes the app as built on 2026-08-05, after the revamp in
[`16-ui-revamp-plan.md`](./16-ui-revamp-plan.md).

This is the successor to the pre-revamp audit (`15-ui-inventory.md`, which was
never committed and is no longer on disk). For what changed and why, see
[`16-ui-revamp-plan.md`](./16-ui-revamp-plan.md).

Every screen is described in enough detail to picture it without seeing it: where
things sit, how big they are, what colour they are, what they do when touched,
and what they look like while loading, empty, or broken. Exact values are given
wherever the code fixes them.

The last section, §14, is written specifically for the **two-colour question**:
it inventories every place colour currently appears, which of those are load
bearing, and which are neutral surfaces waiting for a second accent.

---

## 1. The visual language

### 1.1 Colour, and what each one means

Dark theme only. Ten surface and text tokens, five semantic ones. Defined as CSS
custom properties in `styles/index.css`, mapped into Tailwind so class names like
`bg-panel` and `text-green` resolve to them.

**Surfaces**, darkest to lightest. This is a real ramp: each step is visibly
lighter than the last, which is what lets a card read as sitting *on* the page
rather than floating in a void.

| Token | Hex | What it is |
| --- | --- | --- |
| `bg` | `#0b0c0f` | The page. Neutral ink, very slightly blue. Not black, not green |
| `panel` | `#111318` | Card surface. Clearly lighter than the page |
| `panel-raised` | `#171a20` | Inputs, hover, chips, the selected segment |
| `overlay` | `#1d212a` | Dialogs and menus, which float above the page |
| `hairline` | `#23272f` | The default 1px border on every card |
| `line-strong` | `#333945` | Hover borders, selected borders, the edge of an overlay |

**Text**, all contrast-checked against `panel`:

| Token | Hex | Contrast | Use |
| --- | --- | --- | --- |
| `text` | `#eef0f4` | 16.3:1 | Primary. Slightly off-white, easier on the eye than pure white |
| `text-secondary` | `#9aa2b1` | 7.2:1, AAA | Sublines, labels, inactive |
| `text-tertiary` | `#7c8593` | 5.0:1, AA | Meta, timestamps, disabled, counts |

**Semantics.** Each has exactly one job. This is the single most important rule
in the current system, and the thing to preserve when adding a colour:

| Token | Hex | Reads as | Job, and only this job |
| --- | --- | --- | --- |
| `green` | `#c6f440` | Acid lime, yellow-leaning, very bright | **Money.** Currency figures, balances, payouts, winnings, ROI. If a number is not currency, it is not lime |
| `action` | `#f2f5ef` | Near-white, faintly warm | **The primary action.** Filled buttons, the send button, your own chat bubble, checked boxes, unread badges |
| `live` | `#4fd1e0` | Clear cyan, the only cool hue | **Happening now.** Presence dots, searching dots, in-progress states, the queue, "Linked" |
| `red` | `#ff5f48` | Orange-red | Loss, error, destructive, the platform fee |
| `warn` | `#f5b93c` | Amber | Pending and caution. **Currently defined but almost unused** |
| `focus` | `#a8c7ff` | Pale blue | The focus ring, and nothing else |

Selection is deliberately **not** a colour. A selected chip, tab, or segment gets
a raised surface plus a `line-strong` border, no hue. That is why the entry
picker inside a contest card can sit two lines above a lime dollar figure without
the two competing.

**Game accents** still exist (`#f0883e` CS2 orange, `#e8a13a` PUBG amber,
`#e6c65c` chess gold, `#e15b4c` Dota brick) but appear in only two places now:
the icon of the **selected** game tab, and chat invite cards, where more than one
game can appear in a single list. They were removed from browse cards, where a
coloured pill and a coloured progress bar told you nothing you didn't already
know from the switcher above.

**Chat avatar accents** are five pastels (`#7fd4ff` sky, `#f0a5ff` pink,
`#ffc46b` peach, `#8ef0b0` mint, `#ff9c8a` salmon), picked by hashing the
person's name so the same person always looks the same. These appear nowhere
outside chat.

### 1.2 Type

**Inter**, loaded from Google Fonts at weights 400/500/600/700 with
`display=swap`. Tabular figures are on globally via
`font-variant-numeric: tabular-nums`, so money never jitters as it updates.

One scale, which overrides Tailwind's defaults so existing class names snap to it:

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

There are no arbitrary sizes left. Headings tighten letter-spacing as they grow,
from ‑0.006em at 18px to ‑0.022em at 30px.

**One mono label survives**, `.label-money`: 11px, uppercase, 0.08em tracking, in
tertiary grey. Its only job is the caption directly above a currency figure:
`ENTRY`, `POT`, `BALANCE`, `EST. WIN`. It appears nowhere else, which is what
makes it read as "this is a number" rather than as decoration.

### 1.3 Shape, depth, motion

- **Radii, three values with a rule.** `card` (12px) for anything sitting on the
  page. `inset` (8px) for anything nested inside a card. `pill` (999px) for
  controls. Circles use `rounded-full`. Nothing else exists.
- **Border.** Every surface on the page carries 1px `hairline`. There are no
  borderless panels. Overlays get 1px `line-strong`.
- **Elevation.** Exactly one shadow token, used only by dialogs, menus, and
  toasts. Cards never cast shadows; they separate by surface value and border.
- **Motion.** Four animations, all disabled under `prefers-reduced-motion` (which
  also clamps every transition to 0.01ms): the 42-second ticker marquee, the
  0.28s rise on the matched card, `animate-pulse` on live dots and skeletons, and
  a 260ms FLIP glide when game pills reorder. The balance also counts up rather
  than snapping.
- **Focus.** One global rule: `:focus-visible` on every interactive element draws
  a 2px `focus`-blue ring with a 2px offset. Mouse clicks don't ring, every
  keyboard path does.
- **Scrollbars** are thin and visible: a 10px track with a `hairline` thumb that
  lightens on hover. Only the ticker marquee hides its gutter.

---

## 2. The shell

Rendered by `AppShell` on every signed-in route. Sign-in, the invite landing, and
admin sit outside it.

### 2.1 Desktop, 1280px and up

Three columns.

**Left: the sidebar, 224px**, with a hairline down its right edge.

- Top: the **logo**, a 28px rounded square in `panel-raised` with a hairline ring
  containing a lime triangle, beside the wordmark "Money Match" at 14px semibold.
- Then **four nav entries**, stacked with 2px gaps, 14px medium, 12px/8px
  padding, 8px radius: **Play, Activity, Social, Wallet**. The active one has a
  `panel-raised` fill and white text; the rest are grey and gain a `panel` fill on
  hover. Social carries a paper-white count badge when you have unread items.
  **Play stays lit on all three contest routes**, and announces itself with
  `aria-current="page"`.
- **Admin** appears below, separated by 8px, for admins only.
- The column ends in a footer above a hairline: a **balance block** (the
  `BALANCE` mono caption over the available figure at 16px semibold in lime,
  linking to Wallet) and below it the **account chip**, a 28px circle with your
  initial beside your username.

**Centre: the content column.** The ticker spans the top, then content sits in a
1440px-max container with 32px side padding. Content and rail form a grid:
content takes the free space, the rail takes a fixed 320px, with a 32px gutter.

**Right: the rail, 320px.** Three blocks with 24px between them:

1. **Balance card.** `BALANCE` caption, the available figure at **30px semibold
   in lime** (the largest number on any screen), then a 12px grey line reading
   "$10.00 in play · +$68.94 all time", then a small "Add funds" link. Hidden on
   Wallet, where it would duplicate the page.
2. **In play.** A "In play" sub-heading with an "All" link to Activity, then up
   to three cards. Each is a compact card with the contest title, its entry on
   the right, the market underneath, and then either **the clear bar** (for a
   pool, because the bar *is* the contest) or the contest's live line.
3. **Queue.** A "Queue" sub-heading with a "Play" link, then up to four rows,
   each a small cyan dot, a username, and an entry amount right-aligned.

Empty states in the rail are single grey lines: "Nothing running. Join a pool to
get started." and "Nobody waiting right now."

**The ticker** spans the full content width with a hairline underneath, 10px
padding. It renders only when real players are queuing. Each item: a 6px cyan
dot, the username in white medium, "wants K/D ratio" in grey, the entry in white
medium, all 12px, crawling leftwards and pausing on hover.

### 2.2 Tablet, 768 to 1279px

The sidebar stays. **The rail does not render** at this width; the content column
takes the full remaining width. The balance is still reachable in the sidebar
footer.

### 2.3 Mobile, below 768px

Sidebar and rail are replaced by two bars.

- **Top bar**, sticky, hairline underneath, 16px/12px padding: logo left; on the
  right a **balance chip** (a `panel` pill with the amount in lime, linking to
  Wallet), a 44px **bell** button with a paper dot when you have unread items,
  and a 36px circular **avatar**.
- **Bottom tab bar**, fixed, hairline on top, respecting the iOS safe area.
  **Four tabs** at roughly 94px each on a 375px screen, each a minimum of 52px
  tall: a 22px stroke icon over an 11px label. Active is white, inactive grey.
  The icons are a lightning bolt (Play), a pulse line (Activity), a group of
  people (Social), and a wallet (Wallet). Social shows a paper count badge on the
  icon's top-right when unread.

### 2.4 Toasts

Bottom-centre on mobile (96px up, clearing the tab bar), bottom-right on desktop.
A pill in `overlay` with a `line-strong` border and the one shadow, 16px/10px
padding, 14px medium text, led by an 8px dot: paper for success, red for error,
cyan for info. Maximum three, each lasting 4 seconds.

---

## 3. Shared building blocks

**`Card`** is the one surface primitive: 12px radius, 1px hairline, `panel` fill,
no shadow. Three tones: `default`, `raised`, and `overlay` (which swaps in the
stronger border and the shadow, for dialogs). Passing `interactive` adds the
hover border.

**`PillButton`** is the only button. Fully rounded, semibold, five variants and
three sizes:

| Variant | Looks like |
| --- | --- |
| `primary` | Solid near-white fill, dark ink text. The loudest thing on any screen |
| `secondary` | `panel-raised` fill with a hairline border, white text |
| `outline` | Transparent with a hairline border, white text |
| `text` | No box, grey label that turns white on hover |
| `danger` | Transparent with a red border, red text |

Sizes are `sm` (12px/6px padding, 12px text), `md` (16px/8px, 14px), `lg`
(20px/12px, 14px). Disabled drops to 40% opacity. No call site overrides its
padding any more.

**`SectionHeader`** is the only heading component. Three levels: `page` (24px
semibold, `h1`, 24px bottom margin), `section` (20px semibold, `h2`), `sub` (14px
semibold, `h3`). Takes an optional grey `hint` line and a right-aligned `action`
slot.

**`Segmented`** is the one "pick one of a few" control, used for the contest-mode
switcher, the entry amount inside a card, and the Social sub-tabs. A recessed
`panel` track with a hairline border and 4px padding; the selected option is a
`panel-raised` pill with an inset `line-strong` ring. Renders as a real tablist.

**`WagerCard`** is the joinable contest, and its structure is the most important
layout in the product. Top down:
1. A row with the metric or field size in 12px grey on the left, and an optional
   `panel-raised` tag pill on the right (difficulty, "top 3 paid", "BLITZ").
2. The title at 18px semibold.
3. **The headline number** at 30px semibold, e.g. `1.80`, with "to clear" beside
   it in 12px grey.
4. **The clear-rate meter**: a 6px track with a grey fill proportional to how
   often you clear that bar, over the line "16% of your recent matches clear it"
   with the percentage in white.
5. `ENTRY` in the mono caption, then a **segmented control of dollar amounts**,
   defaulting to the middle preset.
6. A row with `EST. WIN` over the payout at 18px semibold **in lime**, and on the
   right "3 of 4 in" (or "1v1") in 12px tertiary grey.
7. A full-width `lg` primary button: "Join pool", "Join tournament", "Find match".

Changing the entry updates the payout in place. There is one card per contest,
never one per stake.

**`ClearBar`** is the signature object, described in §13.

**`CardGrid`** caps its columns by card count: one card renders in a 384px-max
single column, two in a 768px-max two-column grid, three or more in the full
responsive 1/2/3 grid. A single contest never sits alone in a wide grid looking
like a loading error.

**`ExpandableCard`** is a `Card` with a header row (optional left slot, 14px
title, 12px subline, right value) and a chevron that rotates 180° to reveal a
hairline-separated body.

**`ListRow`** is the flat alternative: a hairline underneath, 12px padding,
optional left slot, title and subline, right slot.

**`FilterBar`** is a small pill toggle with a hamburger icon, the word "Filters",
and a paper badge showing the active count. Opening it drops a `Card` of chip
rows. Chips are hairline pills; selected gains a `panel-raised` fill and a strong
border.

**`GameTabs`** is the game switcher: pills with the game's icon and name. The
selected one gets a `panel-raised` fill, a strong border, and **its icon in the
game's accent colour**. Selecting a game moves it to the front and the others
glide.

**`EmptyState`** is a **dashed** hairline box, 64px vertical padding, centred: a
16px semibold title, a 14px grey line, and usually a button. **`ErrorState`** is
the same with a dashed red-tinted border and a "Try again" button.

**`Skeleton`** blocks pulse in `panel-raised` at 8px radius. `SkeletonList`
stacks rows shaped like real content. This is the only loading treatment in the
app.

**Form controls** (`TextInput`, `TextArea`, `Select`, `Checkbox`, `RadioRow`) all
share one treatment: pill-shaped, `panel-raised` fill, hairline border that
lightens on hover. The select draws its own chevron; the checkbox is a 20px
rounded square that fills paper-white with a dark tick; the radio is a 16px
circle with a paper dot. No native browser control is visible anywhere.

---

## 4. Play: the contest surface

All three contest modes share a header and differ only in their cards.

**The header**, on all three: a **`ModeSwitcher`** segmented control reading
**Solo pools | Tournament | Head-to-head**, then the game switcher beside it
(wrapping to its own line on mobile). No page title above it; the title comes
after any status banner.

Then a `page` heading, then a **"How it works"** disclosure: a small grey button
with an info circle. Open on your first visit to that surface, and once you close
it, it stays closed forever (remembered in `localStorage` per surface). The
explanatory prose lives inside it, so a returning player never scrolls past it.

### 4.1 Solo pools, `/pools`

Heading "Solo pools". The disclosure reads: "Three or four similar-skill players
each get a personal bar quoted from their own baseline. Clear your bar in your
next match and you take a share of the pot. You are playing the number, not the
other players."

Above the heading, when relevant: the **getting-started card** (a `Card` with
"Getting started 1 of 3", the count in grey, then three rows each with a 20px
circle that fills paper-white with a dark tick when done; incomplete steps are
white underlined links, complete ones are struck through in tertiary grey).

Then a `FilterBar` (Metric, Difficulty; entry is no longer a filter because it
lives inside the cards), then **one `WagerCard` per bar**. A metric with three
difficulties produces three cards reading `Clear 1.65`, `Clear 1.80`, `Clear
2.00`, tagged easy/medium/hard, with visibly different clear-rate meters. When
more than one metric is open, each gets a `section` heading above its grid.

**In-flight states** appear above the heading:

- **Searching**: a `Card` with a 10px pulsing cyan dot, "Finding your room" in
  14px medium, "Matching you with players of a similar standard." in 12px grey,
  and a "Cancel" text button on the right.
- **Formed**: a `Card` with a cyan dot beside "ROOM FORMED" in 12px uppercase
  cyan; a 20px semibold line "medium K/D ratio · bar 1.75"; a 12px grey line "4
  players · pot $40.00"; and **on the right, the clear bar** showing your actual
  baseline against the room bar. Underneath, in 14px white: "Your $10.00 is in
  escrow, so you can now play your Counter Strike 2 game. Clear the room bar in
  your next match to take your share." Demo accounts also get a "New pool"
  outline button.

While a pool is in flight every Join button is disabled.

### 4.2 Tournament, `/tournament`

Heading "Tournaments". The disclosure explains best-of-N scoring and the top-3
split.

**One card per metric.** The card shows the field size where the metric label
normally sits ("16 players"), a "top 3 paid" tag, the metric as the title, and
the explanatory line as its subtitle (tournaments have no bar, so no headline
number or meter). `POT IF FULL` sits where `EST. WIN` sits on a pool card.

**Forming** is the same banner shape reading "Finding your field". **Formed**
becomes a standings `Card`: a cyan dot beside "LIVE STANDINGS" (or a grey "FINAL
STANDINGS" when settled), the metric at 20px, then a `ListRow` per player
showing `#3 kvem_` with your own row in **semibold white** and "(you)" appended,
a score subline, and a lime payout on the right once settled. A grey footer gives
the pot.

### 4.3 Head to head, `/play`

Heading "Head to head". **One card per market**, in 1v1 mode: no headline number,
the market as the title, the resolution note as the subtitle, `YOU WIN` over the
lime payout, and "1v1" where the fill count sits.

Below the grid, when anyone is queuing, a **"Waiting to play"** section with the
hint "Take one of these and you skip the queue.", then a `ListRow` per player
with a small cyan dot, their name, "K/D ratio · $10.00", and a `secondary`
"Match" button. When nobody is waiting the whole section is absent rather than
showing an empty heading.

**The slip** replaces the grid entirely once a match is in flight. It is a
`Card`-styled panel, full width on mobile and 354px on desktop, with four states:

- **Searching**: a 12px pulsing cyan dot beside "Searching…", a grey line that
  changes as the skill band widens, a "Waiting 34s" counter, and "Cancel search".
- **Matched**: the **VersusCard**, then the forecast in 12px grey, then a rake
  line ("Both stake $10.00 · winner takes $18.00 · $2.00 platform fee"), then a
  full-width primary **"Confirm & stake $10.00"** and a "Decline" text button.
- **Active**: the same card plus either an external "Go play your game ↗" button
  or an inset block explaining that your next finished match is graded
  automatically.
- **Idle**: "Pick a market to start".

**VersusCard** is a `panel-raised` card with a hairline that rises and fades in
over 0.28s. Two mono captions on top (status left, market right). Two player
boxes with a hairline "VS" pill between them: **your box** has a `line-strong`
border and a `panel-raised` fill with a 36px **paper-white circle** holding your
dark initial; the opponent's is plain. Below a hairline, `POT` with the amount
and `YOU'D WIN` with the amount **in lime**, both 18px.

---

## 5. Activity, `/activity`

Page title "Activity" with the hint "Every contest you have played, newest
first." Column caps at 640px.

A stack of `ExpandableCard`s with 8px gaps. Collapsed, each shows:

- a **10px dot**: lime if you won (money), cyan if it is still running, tertiary
  grey once settled;
- a title, `vs jordn_cs · K/D ratio` or the pool's own title;
- a subline combining state, result, and age: "Won · You 1.42 · jordn_cs 1.10 ·
  2h ago". States read "Awaiting confirmation", "In progress", "Push · refunded",
  "Refunded", "Won", "Lost", "Settled";
- the **net amount** on the right, lime with a `+` for a win, grey for a loss, or
  "$10.00 in play" while running;
- a chevron.

**In-flight contests carry a live line** under the header: a 6px dot (pulsing
cyan while live), the word "LIVE" or "Final" in 12px uppercase grey, and a
description such as "K/D · you 1.42 · opp 1.10", "move 24 · your move", or "#3 of
16 · kills 14".

Expanded, a match shows opponent, map, mode, and a timestamp, then a
**three-column stat table** (Stat / You / Opponent) with a `panel-raised` header
row, where the better of two numbers is **semibold white** and the other drops to
secondary grey. Then a row of fact chips: 8px-radius `panel-raised` blocks with
an 11px uppercase label over a 14px value. Pools and tournaments skip the table
and show only chips.

Two actions live in the body: **Rematch** (an outline button on settled matches,
which toasts "Rematch sent to kvem_") and **Contest this result** (an outline
button opening a bordered box with a textarea, "Tell support what looks wrong",
plus Submit and Cancel). Once filed it collapses to a grey strip reading
"Contested · under review".

A newly settled contest also fires a toast, but only for transitions that happen
while you are watching.

Empty: "No contests yet / Join a pool and your results land here automatically."
with a "Browse solo pools" button.

---

## 6. Wallet, `/wallet`

Page title "Wallet", hint "Play money until full launch." Column caps at 640px.
The rail hides its balance card here to avoid saying the same number twice.

**The hero**: a `Card` with `AVAILABLE` in the mono caption, then the figure at
**30px semibold in lime**, then one 12px grey line: "$26.00 in play · +$68.94 all
time". This replaced a three-cell bar that gave equal weight to three numbers of
very unequal importance.

**Add funds** and **Cash out** are `sub` headings over rows of preset pills.
Tapping one acts immediately. When your balance is zero, Cash out shows "Nothing
to cash out yet. Win a contest and it lands here." instead of an empty row.

**Recent** is a stack of ledger cards, each with a **8px semantic dot** (lime for
credits, red for the platform fee, tertiary grey for debits and holds), a human
label ("Added funds", "Entry held", "Winnings", "Platform fee"), a relative
timestamp, and a signed amount on the right. A "Load more" outline button appears
when there are further pages.

Loading replaces the body with a 112px skeleton block and three skeleton rows.

---

## 7. Social, `/social`

Three sub-tabs rendered as a `Segmented` control: **Inbox | Leaderboard |
Friends**. Inbox is first and is the default, and carries a paper count badge for
unread messages plus notifications. No page title.

### 7.1 Inbox

A two-pane messaging surface in a `Card`-styled panel with the overlay shadow:
a 368px conversation list beside the open thread on desktop, one pane at a time
on mobile with a back arrow.

**The list** pins **Notifications** and **MoneyMatch Support** above the direct
messages. Each row is a 40px initials avatar with a presence dot (cyan online,
hairline offline), a name, a preview line, a relative time, and a paper count
badge. The active row gets a `line-strong` left edge and a `panel-raised` fill.

**The thread** has a header with the avatar and an "Active now" / "Offline" line
(cyan dot when online), then a scrolling transcript with day dividers, then the
composer. **Your messages are paper-white bubbles with dark text**, right
aligned; theirs are `panel-raised` with a hairline, left aligned. System lines
are centred grey pills. The composer is a rounded textarea with a paper-white
circular send button and a `+` invite menu that rotates 45° and turns paper-white
when open.

Since the revamp the chat runs on **the same type and spacing scale as the rest
of the app**: 14px body, 40px avatars, the shared radii and tokens. It no longer
reads as a bolted-on second product.

Full detail lives in [`14-inbox-messaging.md`](./14-inbox-messaging.md).

### 7.2 Leaderboard

A 640px list of `ListRow`s. Each has the rank in a 24px grey column, the username
(**semibold white** with "(you)" appended if it is you), a "12 contests" subline,
and a right-aligned ROI percentage, **lime when positive** (it is a return on
money) and grey when negative. Empty: "Nobody is ranked yet".

### 7.3 Friends

A 640px column. A pill input ("Add by username or code (MM-…)") beside an "Add"
button, then your own friend code in 12px grey.

Then up to three `sub`-headed sections. **Requests** rows carry primary "Accept"
and text "Decline". **Friends** rows carry a 10px presence dot (cyan online), the
username, "Active now" / "Offline", and three `sm` buttons that wrap rather than
crowd the name: `secondary` **Message**, primary **Challenge**, and text
**Remove**. **Sent** rows show "Pending" with no actions.

### 7.4 The Challenge dialog

A full-screen 70% black overlay centring a 448px `overlay`-tone card. An 18px
title, a "Close" text button, a row of three game pills, then `MARKET` over a
scrollable list of **styled radio rows** (a 16px circle that gains a paper dot,
on a `panel-raised` fill when selected), an optional speed row, then `ENTRY` over
preset pills. At the bottom, a primary "Send challenge" and an outline "Copy
invite link"; choosing the link swaps in a read-only field and a "Copy" button.

---

## 8. Profile, `/profile`

Page title "Profile". Column caps at 640px.

An identity row: a 48px `panel-raised` circle with your initial, your username at
18px semibold, "Member since 3/14/2026" in 14px grey.

Four `sub`-headed sections:

**Games** is the `LinkGames` list, hairline-divided. Each row has a 20px circular
checkbox on the left that fills with the **game's accent colour** and a dark tick
when the game is in your switcher; the game's clean name (never the raw
`CS2 — FACEIT` the server sends); a status line ("kvem_ · 1,284 games", "Link it
to play", "Linking coming soon"); and for linked games a skill badge in the
game's accent on a faint wash of it, plus a plain "5 win streak" pill. On the
right: an outline "Link" button, or a small "Refresh" text button beside
**"LINKED" in uppercase cyan**. Pressing Link expands an inline pill input with
"Verify" and "Cancel".

**Limits** has three dollar fields (label left, a grey `$` and a 96px
right-aligned pill input on the right), a pending-raise note where relevant, a
read-only "Max concurrent contests" row, and a primary "Save limits". Below a
hairline, **Take a break** offers 1 / 7 / 30 day outline buttons; clicking one
swaps in a red "Confirm 7-day break" and a grey "Cancel".

**Notifications** is one button toggling between primary "Enable notifications"
and outline "Turn off notifications", with a cyan "On" beside it when active.

**Security** (hidden for demo accounts) is an outline "Change password" opening a
two-step inline form with inline validation in red.

At the bottom: an outline "Sign out", then a bare **red "Self-exclude"** that
swaps into "This is permanent. Continue?" with a red confirm and a grey cancel.

---

## 9. Sign-in, `/signin`

No shell. A centred 384px column on the flat page background. At the top, the
44px lime triangle mark and a **three-segment progress bar** whose completed
segments are paper-white.

**Step 1, Auth.** A centred 20px title, a grey subtitle, then a full-width
outline "Continue with Google", an "or" divider, a form with styled email and
password inputs, a full-width primary submit, and a text button toggling between
sign-in and sign-up. Errors are centred red text in plain language. Below a
hairline, a text button: "Skip sign-up · enter the demo →".

**Step 2, Profile.** Labelled fields: a username input with a hint, a **styled
select** for the residence state (drawing its own chevron), and a **styled
checkbox** for the 18+ attestation. A full-width primary "Continue", disabled
until valid.

**Step 3a, Games.** A two-column grid of game cards, each with a circular
checkbox top-right that fills with the game's accent, the game's 24px accent icon,
its name, and a "SOON" pill where relevant.

**Step 3b, Link.** The `LinkGames` list narrowed to your picks, then "Enter Money
Match".

---

## 10. Invite landing, `/i/:token`

Public, no shell. A centred 384px column. The **same 44px triangle mark** as
everywhere else (this page used to carry a different logo). Then "kvem_
challenged you" at 20px, a line reading "K/D ratio for **$10.00**" with the
amount in lime, and one of four actions: "Sign in to accept", "Finish setup to
accept", "Accept challenge", or a red "This challenge is no longer open."

---

## 11. Admin, `/admin/*`

Deliberately outside the design system and untouched by the revamp: white
background, black text, 13px monospace, dense bordered tables, square buttons,
green `#080` for OK and bold red `#b00` for anything wrong. It is an internal
tool, and it should stay looking like one.

---

## 12. Responsive behaviour, summarised

| Width | Nav | Rail | Balance lives | Contest grid |
| --- | --- | --- | --- | --- |
| < 768 | Bottom bar, 4 tabs | None | Top-bar chip | 1 column |
| 768 to 1023 | Sidebar 224px | None | Sidebar footer | 2 columns |
| 1024 to 1279 | Sidebar 224px | None | Sidebar footer | 3 columns |
| 1280+ | Sidebar 224px | 320px, right | Sidebar footer + rail | 3 columns |

---

## 13. The signature: the clear bar

The product's one loud element, and the thing a stranger should remember.

A horizontal track showing **your number** against **the number you have to
beat**, with the gap between them shaded. The target is a full-height white tick
that overhangs the track top and bottom; the ground you have already covered is a
filled bar to its left; the distance still to cover is washed in the cyan live
tone at 25% opacity. Underneath, two 12px lines: "your avg **1.42**" on the left,
and either "need +0.38" in tertiary grey or "clear" in lime on the right.

It scales so the target sits at about 78% of the track, leaving room for an
overshoot to read as an overshoot rather than as a full bar.

It appears in three places, always meaning the same thing: the **formed-room
banner** on Solo pools, the **in-play card** in the rail, and (via the live line)
**Activity**. On browse cards, where the server quotes a bar and a clear rate but
not your baseline, the card shows the **clear-rate meter** instead rather than
inventing the "you" end of the bar.

---

## 14. Where colour lives today, for the two-colour question

This section exists for the revamp you are planning. It is an inventory, not a
recommendation.

### 14.1 What is load bearing and must not move

These three carry meaning that the layout does not otherwise express. Changing
what they mean would cost real clarity:

| Colour | Every place it appears |
| --- | --- |
| **Lime, money** | Balance in the sidebar footer, rail, mobile chip, and Wallet hero; the payout on every contest card; "You'd win" on the VersusCard and slip; ROI on the leaderboard; net amounts and payout dots in Activity and the Wallet ledger; the entry amount on the invite landing; "clear" on the bar |
| **Paper, primary action** | Every filled button; the chat send button and your own message bubbles; checked checkboxes and radios; unread badges; completed steps in the progress bar and the getting-started checklist; your circle on the VersusCard |
| **Red, loss and danger** | Error text, the platform-fee dot, self-exclude, "Blocked", the dashed border on `ErrorState` |

### 14.2 What is currently thin, and is the natural home for a second colour

**Cyan (`live`) is deliberately underused.** It is bounded to dots, one-word
labels, and the 25% wash inside the clear bar. It never fills a shape, never
appears as a button, never runs across a sentence. That restraint was a hedge
against the lime-plus-cyan crypto look, and it means **cyan is the obvious
candidate to promote** if you want a second main colour: the meaning is already
established ("happening now"), it is already in the token set, and widening its
use would not require re-teaching anyone anything.

Places cyan could legitimately expand into, in rough order of payoff:

1. **The formed-room and standings banners.** Currently a hairline card with a
   small cyan label. A cyan-tinted surface or left edge would make "you have
   something running" visible from across the room, which is the one state the
   app most wants you to notice.
2. **The in-play cards in the rail.** Same argument, same component.
3. **The live line in Activity.** Currently a 6px dot and grey text.
4. **The ticker.** Currently a cyan dot on grey text.
5. **The gap segment of the clear bar**, which could carry more weight than 25%.

**Amber (`warn`) is defined and effectively unused.** It is a free slot if you
want a third semantic later, most obviously for "pending" and "awaiting
confirmation" states, which currently borrow the live tone.

### 14.3 Surfaces that are currently pure neutral

If you want a second colour to be felt rather than merely present, these are the
large areas that currently carry none, listed by how much screen they occupy:

- **The page background** (`#0b0c0f`), which is a flat neutral ink everywhere.
  The pre-revamp app had two lime corner glows here; they were removed as
  decoration. A very low-opacity wash in a second hue is the single largest
  available surface.
- **Card fills** (`panel #111318`), which are neutral on every screen.
- **The sidebar**, which is transparent over the page with only a hairline edge.
- **Section headings and mono captions**, which are all grey.
- **The empty and error states**, whose dashed borders are hairline and red-tinted
  respectively.
- **The skeleton blocks**, which pulse in neutral `panel-raised`.

### 14.4 Two constraints worth keeping whatever you pick

1. **Selection must stay structural.** A selected chip, tab, or segment currently
   uses a raised surface and a stronger border, no hue. That is what lets the
   entry picker sit two lines above a lime payout without competing. If a second
   colour takes over selection, that conflict comes back.
2. **One meaning per colour.** The whole gain of the revamp was that lime stopped
   meaning five things. A second main colour is worth adding only if it arrives
   with a single job that is currently being done by weight, position, or nothing
   at all.

### 14.5 One honest problem, unrelated to colour

`filledSpots()` in `lib/spots.ts` invents the "3 of 4 in" figure on every contest
card by hashing the card key into the range between half full and one short of
full. It is not a live count. On a real-money product that is fabricated social
proof, and it is worth a product decision before any further visual work makes it
more prominent.
