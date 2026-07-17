# Design System & Screen Spec

Source of truth: [`docs/design/moneymatch-design.pdf`](../design/moneymatch-design.pdf)
(13 pages). This doc translates it into buildable tokens and per-screen specs.
When in doubt, open the PDF — match it closely; the MVP UI bar is "acceptable
for real users," and this design already is.

The PoC's UI (lime-on-dark, 7-tab sidebar, dense cards) is **replaced** by this
design. Reuse PoC component *logic* (hooks, formatting, countdowns), not its look.

---

## 1. Visual language

Minimal, near-monochrome, Cash-App-adjacent. Pure black canvas, hairline
separators, a single vivid green for money/positive/brand, white pill buttons
for secondary actions, green pills for primary.

### Tokens (CSS custom properties; Tailwind maps to these)

```css
:root {
  --bg: #000000;            /* page canvas */
  --panel: #0e0f0e;         /* right-slip / card panels */
  --panel-raised: #161716;  /* selected nav item, avatar chips */
  --hairline: #1e201e;      /* 1px separators, card borders */
  --text: #ffffff;
  --text-secondary: #8b9089;/* labels, sublines */
  --text-tertiary: #565b55; /* footer breadcrumbs, disabled */
  --green: #00d632;         /* brand + money + CTAs (sample from PDF before finalizing) */
  --green-dim: #0a3d16;     /* green outline/glow on selected cards */
  --red: #ff4d2e;           /* BLOCKED, self-exclude, losses */
  --radius-pill: 999px;     /* all buttons are pills */
  --radius-card: 12px;
}
```

Type: a clean grotesk sans (Inter is fine) — regular weights; bold only for
names/amounts. Big money numbers (balance, "You'd win") are large, bold,
tight-tracked; the "You'd win $18.00" figure renders in `--green`.
Footer breadcrumb (bottom-right, e.g. `PLAY · WAGER SLIP`) is uppercase,
letter-spaced, monospace, `--text-tertiary` — keep it; it doubles as a QA
locator for screenshots/e2e.

Buttons: pill-shaped. Primary = solid green, black text. Secondary = white,
black text. Tertiary = outlined hairline, white text. Text-only for "Cancel"/"Back".

Cards/rows: transparent background with `--hairline` top/bottom rules (lists) or
1px-bordered rounded cards (pool tiers, tournaments). Selection state = green
1px border + subtle green glow + green check-circle (see PDF p.2, p.4).
Stat grids inside cards: 4 columns, tiny uppercase gray label over bold value.

## 2. Layout

- **Left sidebar, ~184 px, full-height, black.** Logo top (green rounded-square
  glyph + "Money Match" wordmark). Nav: Play, Pools, Tournament, Activity,
  Wallet — active item = `--panel-raised` rounded row. Bottom: notification bell
  (green unread dot → Inbox) + avatar chip + username.
- **Main column** (~left 60%): page content. Play/Pools/Tournament use a
  **right slip panel** (~354 px, `--panel`, rounded 16 px) that holds the
  contextual action flow; Activity/Wallet/Inbox/Profile are single-column.
- Balance header (Play only): tiny gray "Balance" label, huge `$1042.94`, gray
  subline `$26.00 in play`.
- Game switcher: text tabs (Chess / CS2 / Dota 2) with green underline on active.
- Mobile: not in the PDF — do a simple collapse (sidebar → bottom tab bar);
  desktop is the demo target.

## 3. Screens (PDF page → spec)

| # | Screen | Key elements |
| --- | --- | --- |
| 1 | **Play — markets** | Market rows per game (name + subline e.g. "Next FACEIT match · 24h" + `×1.80` + radio). Below: **"Waiting to play"** — real open tickets from other users (avatar, name, `market · $entry`, white **Match** pill). Right slip: empty state "Pick a stat to start". |
| 2 | **Play — wager slip** | Selected market gets green check; slip shows "Wagering on {market}", entry presets **$5/$10/$25** (green-outlined pill on selected), "You'd win **$18.00** on a $10.00 wager" (derived, green), primary **Find match**, secondary **Invite friend**, text **Cancel**. Find match → queue state (spinner, band info, cancel) → matched → confirm. |
| 3 | **Play — invite friend** | Slip variant: friend list with green presence dots + **Invite** pills, **Copy invite link** outline button, **Back**. |
| 4 | **Pools — new pool** | Tier cards **Easy/Hard/Brutal** ("~28% of players clear it", `×1.60/×2.40/×4.80`, 4-stat grid: K/D ≥1.55 · ADR ≥87.3 · HS% ≥47.1 · Kills ≥17). Selected = green border. Slip: "Your pool", tier summary, clear rate, payout, entry presets, "Clear it and win **$16.00**", primary **Find pool**. |
| 5 | **Pools — open pools** | Same tiers as joinable rooms: "Easy room · 12 playing" + **Enter** pill. Sub-tabs top-right: New pool / Open pools. |
| 6 | **Tournament — list** | Sub-tabs: Tournaments / Leaderboard / Friends; game tabs below. Cards: name + JOINED chip, "Best ADR · ends in 1d 07h · entry $10", prize pool $ (green), 1st/2nd/3rd split grid, progress bar `8/10 players`. Right slip: live standings (rank, name, stat; you highlighted green), "You're in · 2 spots left". Footnote: "Play your normal matches during the window — your best stat is recorded automatically." |
| 7 | **Leaderboard** | Ranked rows: number, avatar, name, green `+31.2%` (ROI). You highlighted. |
| 8 | **Friends** | Add-by-username input + green **Add**; pending request row with green **Accept**; friend rows with presence dot + white **Challenge** pill. |
| 9 | **Activity** | Unified rows: status dot (green=live/won, gray=done), title ("vs kvem_ · K/D race"), subline state (In progress / Settling / Won / Push · refunded / Refunded), right-aligned amount (+$18.00 green for wins). |
| 10 | **Wallet** | Title + "Play money — no real deposits yet." Three-cell stat bar: Available / In escrow / Lifetime (+$68.94 green). **Add funds** presets $10/$25/$50/$100 (outline pills). "Recent" ledger rows: memo + relative time, signed amount (− gray, + white, wins green). |
| 11 | **Inbox** | Notification rows: unread green dot, text ("Room filled — kvem_ took side B", "jordn_cs challenged you · $5"), age, action pills (View / Respond). |
| 12 | **Profile** | Avatar + username + "Member since". **Linked games** rows: "Chess — Lichess" + LINKED (green) / BLOCKED (red) status text. **Limits** rows (Daily loss cap, Daily entries). Action pills: Sign-in flow, **Self-exclude** (red text). Linking flow (not in PDF): row click → username input → verify via server → LINKED. |
| 13 | **Sign-in** | Centered: logo, 3-segment progress bar (green active), "Sign in / Play skill-based matches for real payouts.", **Continue with Google** (outline), **Continue with email** (green). Steps: auth → username + state/18+ attestation → link first game. |

## 4. The multiplier rule (legal-critical)

The design shows `×1.80` on markets and `×1.60/×2.40/×4.80` on pools. These are
**derived displays, never configured odds**:

- H2H: multiplier ≡ `2(1 − rake)` — with 10% rake, exactly ×1.80. It cannot be
  set per-player or per-outcome. Tooltip copy: "Both stake $10 · winner takes
  $18 · $2 platform fee."
- Pools: the pot is entrant-funded and clearers **split the pool minus rake**;
  the tier multiplier is an **estimate** derived from the difficulty's design
  clear rate (`×… ≈ (1 − rake) / p_target`). The tier cards' stat thresholds
  are **personalized** — quoted from the viewer's own baseline
  (`μ + k·σ`, see Phase 4), so two players see different numbers on the same
  Easy card; the PDF's values are one player's view. UI copy must say
  "estimated payout — actual payout is your share of the pool." A fixed
  guaranteed multiplier would be house-banked and is prohibited
  (see `docs/product/overview.md` §10.4). Demo money softens this at MVP, but
  build the pooled math now so real money doesn't require a rewrite.
- Rake is always visible pre-commit (slip line item), satisfying the
  responsible-gaming disclosure rule.

## 5. Component inventory (build once in `apps/web/src/components/ui`)

`SidebarNav`, `BalanceHeader`, `GameTabs`, `SubTabs`, `MarketRow`, `SlipPanel`
(state machine: empty → configure → searching → matched → confirmed), `PillButton`
(primary/secondary/outline/text), `PresetSelector` ($ presets), `StatGrid`,
`TierCard`, `ListRow` (avatar + title/subline + right slot — used by waiting,
friends, activity, inbox, ledger), `ProgressBar`, `StandingsList`, `StatusDot`,
`AmountText` (signed money coloring), `EmptyState`, `Toast`, `FooterBreadcrumb`.

Port from PoC (adapt, don't copy blindly): `format.ts` (currency/pct — switch to
cents), countdown logic from `ActiveContractCard`, toast queue from `useToasts`.
