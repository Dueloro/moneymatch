# money match — Implementation Report (ground truth)

> **What this is.** An honest, code-verified description of what is actually
> built in this repository right now — what works end-to-end, what is mocked for
> the demo, and what exists but isn't wired up. It was written by reading every
> source file, not the older design docs. Where the live code disagrees with the
> aspirational docs, this file follows the code.
>
> If you only read one section, read **§13 (What works vs. mocked vs. not wired)**
> and **§14 (Known rough edges / honesty notes)**.

---

## 0. Naming (read this first)

Three names coexist because the project pivoted:

| Name | Where it appears | Meaning |
|---|---|---|
| **clutchbook** | repo folder, this workspace, the Electron prod URL `clutchbook.app` in `electron/main.ts` | The old brand / repo name (legacy). |
| **money match** | the UI brand wall, header, FastAPI title (`"money match API"`), most doc copy | The **current** product name shown to users. |
| **money-match** | `package.json` `name` field | npm package id. |

The product pivoted from a house-banked sportsbook ("Clutchbook") to a
peer-to-peer / pooled **skill-wagering** platform ("money match"). Treat any
"Clutchbook" / odds / house-edge references in code as **legacy** — the only
place that legacy model still lives is the standalone Electron overlay (§11).

---

## 1. What the product is

**money match lets verified players wager (play money, in this demo) on their own
real performance in games they already play.** There is **no house and no odds**:
players stake into an escrowed pot/pool, the result is verified against the
game's real API data, and winners take the pot **minus a fixed platform rake**.
The rake is the only revenue.

There are now **four wagering products** in the app:

1. **Head-to-Head (Lobby tab)** — you vs. a skill-matched bot. Both stake an
   equal entry; whoever wins their next qualifying real game takes the pot minus
   rake. Live for **Chess (Lichess)**, **CS2 (FaceIt)**, **Dota 2 (OpenDota)**.
2. **Solo Pools (Solo Pools tab)** — many players pay into a shared pool against
   a *qualifying standard* (e.g. "chess accuracy ≥82% over ≥20 moves", "CS2 K/D
   ≥1.2 with HS% ≥45"). Everyone who clears splits the pool minus rake; if nobody
   clears, everyone is refunded and the platform earns nothing.
3. **Tournaments (Tournaments tab)** — multi-entrant. N players stake into one
   pool and are ranked. Two formats exist: **leaderboard_pool** (ranked by a
   metric, top finishers split per a prize split like 60/30/10) and
   **single_elim** (a played-out head-to-head bracket, draws force a rematch).
4. **Leaderboard (Leaderboard tab)** — a retention surface ranking players by
   **ROI / record, not raw dollars**.

Plus two "spectate" surfaces inside Active Matches (chess move list; CS2/Dota
match summary), and a **desktop in-game overlay** (Electron) that is a separate,
legacy-shaped demo not wired to any of the above (§11).

Everything is **play money** (wallet starts at $1,000 of virtual currency).

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 18 + TypeScript, Vite 5 |
| Styling | Tailwind 3 (layout utilities) + CSS custom-property design tokens in `src/index.css` |
| Animation | Framer Motion (game-tab reordering, overlay widget); CSS keyframes elsewhere |
| Icons | `lucide-react` |
| Charts | `recharts` is a dependency; the `Sparkline` component uses it but is **not rendered anywhere** in the app |
| Analytics | `@vercel/analytics` (rendered in `App.tsx`) |
| Backend | Python **FastAPI** (async), `httpx` for host API calls, Pydantic v2 schemas |
| Hosting | **Vercel** — static frontend + one Python serverless function at `api/index.py` |
| Desktop overlay | Electron 42 + `vite-plugin-electron` |
| OS window detection | `get-windows` (ESM-only) |
| Tests | `pytest` (backend only) — see §12 |

There is **no database**. The client owns all wallet/contract/pool/tournament
state in `localStorage`; the backend is **stateless** (verifies identity,
generates lobbies, grades settlement against real host data). FaceIt has a small
**in-process cache** for finished-match stats (not persistent).

---

## 3. How to run

Two processes in dev: the Vite frontend (port 5173) and the FastAPI backend
(port 8000). Vite proxies `/api/*` → `http://localhost:8000` (`vite.config.ts`).
**If the backend isn't running, every link / lobby / settlement call fails.**

```bash
# 1. Backend (REQUIRED for linking accounts, lobby, settlement)
python -m uvicorn api.index:app --reload --port 8000

# 2. Frontend web app
npm run dev                      # http://localhost:5173

# Electron overlay variants (separate from the web app — see §11)
npm run electron:dev:mock        # mock game detector, hotkey-driven
npm run electron:dev             # real detector, needs a borderless-windowed game
npm run electron:build           # build the electron bundle

# Backend tests
pytest
```

`npm run lint` = `tsc -b --noEmit`. `npm run build` = `tsc -b && vite build`.

**Health check:** `GET /api/health` → `{"status":"ok","service":"money-match","games":["chess.lichess","cs2.faceit","dota2.opendota"]}`.
If `/api/profile` returns `{"detail":"Not Found"}`, the wrong server is on :8000.

**Environment:** `FACEIT_API_KEY` is **required** for anything CS2 — linking,
the CS2 lobby/settlement, and the FaceIt Lab. Without it, CS2 link calls return
404 (FaceIt service returns `None` when no key is present). Chess (Lichess) and
Dota 2 (OpenDota) need **no key**. See `.env.example`.

---

## 4. Repository layout (actual files)

```
/api                              FastAPI backend (stateless, serverless)
  index.py                        App + all routes (v2.0.0)
  _lib/
    schemas.py                    Pydantic models — SOURCE OF TRUTH for shapes
    lobby.py                      build_contract() + generate() — drafts → OPEN H2H contests (chess/cs2/dota)
    matchmaking.py                find_opponent / find_cs2_opponent / find_dota_opponent; can_pair() stub
    skill_rating.py               Elo expectancy, bracket labels, per-objective rake
    solo_challenge.py             Pooled solo engine: geo-fence, seeding, grading, settlement
    tournament.py                 Multi-entrant engine: leaderboard_pool + single_elim bracket
    leaderboard.py                Seeded ROI-ranked bot field
    spectate.py                   Parse a Lichess current-game payload → move list/clocks
    tracker.py                    Parse FaceIt / OpenDota latest match → compact summary
    lichess_service.py            httpx client over the Lichess public API
    faceit_service.py             httpx client over the FaceIt Data API (needs key; in-proc cache)
    opendota_service.py           httpx client over the OpenDota API (no key)
    adapters/
      base.py                     GameAdapter ABC + NormGame / GameFilters value types
      registry.py                 id → adapter; REGISTERED: chess.lichess, cs2.faceit, dota2.opendota
      chess_lichess.py            Chess adapter (profile, games, H2H settlement)
      cs2_faceit.py               CS2 adapter (profile, match history + telemetry, H2H settlement)
      dota2_opendota.py           Dota 2 adapter (profile, recent matches, H2H settlement)
      stub_cs2.py                 cs2.steam throwaway stub — NOT registered, raises if called

/src                              React web app + electron renderer
  main.tsx                        Routes ?electron / ?overlay / ?lab / (default) to a React root
  App.tsx                         Web app root — owns state, wires hooks, renders tabs
  ElectronApp.tsx                 Overlay renderer root
  getWagerForGame.ts              Overlay seam (returns static LEGACY-shaped demo content)
  types/  index.ts, overlay.ts    Domain types (mirror schemas.py) + overlay shapes
  hooks/
    useWallet, useProfile, useContracts, useSoloPools, useTournaments,
    useSpectate, useTrack, useToasts
  utils/
    apiClient, format, contractText, soloText, tournamentText, games, states,
    playerStats, storage, telemetry, sampleContracts
  components/
    Layout/    Header, Sidebar
    Onboarding/ Landing (brand wall + 18+/state gate)
    Tabs/      Lobby, SoloPools, Tournaments, Leaderboard, ActiveContracts,
               Profile, ResponsibleGaming, Builder, LinkAccounts, MyContests
    Contracts/ ContestCard, ActiveContractCard, SpectatorPanel, MatchTrackerPanel
    Solo/      SoloPoolCard
    Tournament/ TournamentCard (+ played-out bracket renderer)
    Catalog/   GameTabs (game switcher), PreviewContracts (locked/soon previews)
    Lab/       FaceitLab (dev-only sandbox at ?lab=faceit)
    UI/        Badge, Toast, Skeleton, Sparkline (Sparkline unused)
    Overlay/   ContractOverlay (in-game widget), OverlayDemo (fake backdrop)

/electron   main.ts, preload.ts, detector/ (types, polling, mock, index factory)
/tests      test_dota.py, test_faceit.py, test_tournament.py, test_surfaces.py
/docs       overview.md, roadmap.md, IMPLEMENTATION.md (this), old/ (deprecated)
```

---

## 5. Entry points & routing

`src/main.tsx` mounts one of four roots based on the URL query string:

| URL | Root | Purpose |
|---|---|---|
| `?electron` | `ElectronApp` | Transparent Electron overlay renderer. |
| `?overlay` | `OverlayDemo` | Fake game backdrop to test the widget in a browser. |
| `?lab` | `FaceitLab` | **Dev-only** FaceIt data sandbox (no wallet, read-only). |
| (default) | `App` | The full web app. |

---

## 6. Navigation & tab structure (what the user actually sees)

The sidebar (`components/Layout/Sidebar.tsx`) has **7 tabs**:

| Key | Label | Icon |
|---|---|---|
| `h2h` | Head-to-Head | Swords |
| `solo` | Solo Pools | Trophy |
| `tournaments` | Tournaments | Medal |
| `leaderboard` | Leaderboard | BarChart3 |
| `active` | Active Matches | Hourglass (+ count pill) |
| `profile` | Profile | UserRound |
| `responsible` | Responsible Gaming | HeartHandshake |

> **Important difference from the old docs:** there are **no longer** standalone
> "Link Accounts" or "My Contests" tabs. **Linking accounts** and **contest
> history (My Contests)** are now rendered *inside* the **Profile** tab. The
> `TabKey` type confirms this (`h2h | solo | tournaments | leaderboard | active |
> profile | responsible`). After the Landing gate, the app routes you to the
> **Profile** tab (to link an account), not a separate Link tab.

Sidebar footer: linked username, a **Reset balance** button, and a short
disclaimer card.

---

## 7. Domain model (data shapes)

Canonical definitions: `api/_lib/schemas.py` (Pydantic) and `src/types/index.ts`
(TypeScript), kept in lockstep, flat/JSON-friendly so objects round-trip
Python → client → `localStorage`.

### Identity
- **`SkillProfile`** — `username`, `display_name`, `url`, `link_method`
  (`oauth | username`), `game` (adapter id, default `chess.lichess`), `win_rate`,
  `draw_rate`, `total_games`, and **two families of skill descriptors**:
  - Chess: `formats[]` (`FormatStat`: speed/rating/games/provisional) +
    `primary_speed`.
  - Generic (CS2/Dota): `rating` (elo/MMR), `rank_label` (e.g. "Level 10",
    "Legend 5"), `kd`, `avatar_url`.
- **`Speed`** = `bullet | blitz | rapid | classical` (chess only).

### Head-to-Head
- **`Objective`** — `kind ∈ win_h2h | win_under_moves`, optional `moves`.
- **`Bracket`** — `your_rating`, `band_low/high`, `match_quality` (0..1, 1 = even),
  `label` ("Even match" / "You're favored" / "Reach" / …). **Fairness, not odds.**
- **`Opponent`** — `username`, `display_name`, `rating`, `is_bot` (always a bot).
- **`Contract`** — the core object: `entry`, `entrants` (2), `rake_pct`, `pot`,
  `prize = pot*(1-rake_pct)`, `rake`, plus `bracket`, `opponent`, `objective`,
  `speed` (chess time control, or the mode strings `"cs2"` / `"dota2"`),
  `account_id` (the linked account it settles against), `window_hours`, and a
  lifecycle `state`: `OPEN → MATCHED → ACTIVE → RESOLVING → SETTLED | CANCELED`.
  *In the client flow `join()` jumps `OPEN` straight to `ACTIVE` — `MATCHED` is
  defined but unused as an intermediate client state.*
- **`SettleResult` / `SettleResponse`** — server-authoritative grading output;
  `payout` (prize on win, entry on refund, 0 on loss).

### Solo pools
- **`MetricTarget`** — `metric`, `comparator` (gte/lte), `threshold`, plus an
  optional secondary constraint (compound standards).
- **`MetricKind`** — chess accuracy, RL aerial/score, CR crown-tower damage,
  and CS2 (`cs2_kills/kd_ratio/headshot_pct/adr/mvps`) and Dota
  (`dota2_kda_ratio/gpm`).
- **`SoloPool` / `SoloEntry`** — pool, rake, prize_pool, entrants with status
  `LOCKED | CLEARED | MISSED | REFUNDED | BLOCKED_REGION`.

### Tournaments
- **`Tournament`** — `format` (`leaderboard_pool | single_elim`),
  `ranking_metric`, `higher_is_better`, `entry_fee`, `rake_pct`, `max_entrants`,
  `min_entrants`, `prize_split[]`, `entrants[]`, `pool/rake/prize_pool`, and
  `rounds[][]` (the played-out `BracketMatch` list, for single_elim).
- **`TournamentEntry`** — status `LOCKED | PAID | OUT | REFUNDED`, `score`,
  `rank`, `payout`.

### Leaderboard / spectate / tracker
- **`LeaderboardEntry`** — `contests`, `wins`, `win_rate`, `staked`, `net`,
  `roi` (primary ranking key).
- **`SpectateResponse`** — chess move list + clocks + players + turn/result.
- **`MatchTrackerResponse`** — compact headline/subtitle/stat-rows for CS2/Dota.

### Client-only
- **`TabKey`**, **`ToastMessage`** (variant `info | success | win | loss`).

---

## 8. Frontend architecture

### `App.tsx` — the coordinator
Owns top-level state and wires hooks:
- `started` (localStorage `started`) — mock-auth gate. While false renders
  `<Landing>`. `handleStart(state)` stores residence, flips `started`, routes to
  the **Profile** tab.
- `residence` (localStorage `residence`) — US state for the geo-fence.
- `activeTab` (default `h2h`), `navOpen` (mobile drawer).
- **Three linked identities** via three `useProfile` instances: chess (default,
  storage key `profile`), CS2 (`faceit_profile`, game `cs2.faceit`), Dota
  (`dota_profile`, game `dota2.opendota`).
- `selectedGame` + `gameOrder` — a shared game filter; selecting/linking a game
  bumps it to the front of the tab order (persisted to `game_selected` /
  `game_order`).
- Cross-cutting flows it owns: `handleJoin` (H2H validate + escrow + toast →
  Active tab), `onSettle` (apply settlement + win/loss/cancel toast),
  `handleReset` (wipe contracts, solo, tournaments, wallet → $1,000).

### Hooks
- **`useWallet`** — buckets `available` / `escrow` / `locked` (locked unused).
  Starts at **$1,000**, default daily loss limit **$200**. `escrowEntry`,
  `applySettlement`, `setLossLimit`, `reset`, and an rAF-eased `displayAvailable`
  for the header animation. Persists to `localStorage` (`wallet`).
  ⚠️ See §14 — `canJoin`'s loss-cap check is effectively a no-op.
- **`useContracts`** — owns the user's contracts (localStorage `contests`), the
  `active`/`settled` derived lists, the `join()` transition, and the
  **settlement poll loop** (every **15s**, `POST /api/contracts/settle`,
  abortable, re-entrancy guarded). It groups in-flight contracts by
  `(game, account_id)` so chess/CS2/Dota all settle through the right adapter.
  It *also* fetches a chess-only `lobby` on mount — but that `lobby` is **not
  consumed by any rendered component** (see §14).
- **`useSoloPools`** — owns the solo lobby + the user's entered pools
  (`solo_pools`). `join()` → `POST /api/solo/pools/enter` (geo-checked
  server-side). `settle()` builds telemetry for all entrants and
  `POST /api/solo/pools/settle`. **For CS2 it fetches the player's real latest
  FaceIt telemetry** (via the dev route) when a key is present; otherwise (and
  for all other games) it uses the clear/miss button. Bots clear at ~55%.
- **`useTournaments`** — owns the tournament lobby + entered tournaments
  (`tournaments`). `join()` / `settle()` → the `/api/tournaments/*` routes.
  Telemetry for every entrant is **mocked** (`genScore`); the human gets a
  "strong" bias so the demo isn't hopeless.
- **`useProfile`** — `link(username)` → `GET /api/profile?game=`; stores a
  `SkillProfile`. Guards against adopting a stored profile that belongs to a
  different game.
- **`useSpectate` / `useTrack`** — poll the spectate/track endpoints while a
  panel is open (5s / 8s), stopping when the game is finished / not live.
- **`useToasts`** — toast queue.

### `apiClient.ts` endpoints (everything the client calls)
`GET /api/profile` · `GET /api/lobby` · `POST /api/contracts/price` ·
`POST /api/contracts/settle` · `GET /api/solo/lobby` ·
`POST /api/solo/pools/enter` · `POST /api/solo/pools/settle` ·
`GET /api/tournaments/lobby` · `POST /api/tournaments/enter` ·
`POST /api/tournaments/settle` · `GET /api/leaderboard` · `GET /api/spectate` ·
`GET /api/track` · and the dev-only FaceIt Lab routes (`/api/dev/faceit/*`).
`API_BASE = import.meta.env.VITE_API_BASE ?? ''` (same-origin; Vite proxy in dev).

---

## 9. How it looks (visual design)

Dark, premium gaming/wagering aesthetic. Near-black background (`--bg #0a0b0f`),
**electric lime** (`--lime #a3e635`) for brand/primary CTAs/active nav, **emerald**
(`--pos #34d399`) for money/wins (deliberately distinct so lime never means "you
won"), cyan for live/info, crimson for loss, amber for warnings. Headings use a
condensed display font; body a clean sans. Surfaces are layered dark cards with
subtle borders, hover lift, glow shadows, shimmer skeletons, and slide-in toasts.

**Layout.** Sticky 64px blurred **Header** (hamburger on mobile + the `⟁` glyph +
"money match" wordmark + the animated **Available** balance, with escrow appended
inline). Desktop (≥1024px): a fixed **248px sticky left sidebar** + scrollable
main. Mobile: sidebar hidden behind a hamburger that opens a 280px drawer over a
dark backdrop.

### Screen-by-screen (verified against the components)
- **Landing** (pre-auth): centered brand wall (`⟁`, "money match"), a one-line
  pitch, an **eligibility panel** with an **18+ checkbox** and a **US-state
  select**; excluded states show a crimson message and keep **Start** disabled.
  Footer: "Play money only · No deposits".
- **Head-to-Head (Lobby)**: a `GameTabs` segmented switcher (animated reordering,
  per-game linked-check / lock). For a **linked** game: a **Builder** card (chess
  = objective + time control + optional move limit + entry; CS2/Dota = just entry,
  "win your next match") with a **debounced live matchmaking preview** (opponent,
  rating, bracket label, pot/rake, "Win to take" prize) and a two-step **Find
  match → Confirm** button; below it a **grid of open matches** (`ContestCard`,
  each Join → Confirm). For a **live-but-unlinked** game (e.g. before linking
  CS2): a "Not linked" banner + Link CTA over locked sample-contract previews.
  For a **coming-soon** game (Clash Royale, Rocket League): a "Coming soon"
  banner + sample previews.
- **Solo Pools**: page header, `GameTabs`, a **Region bar** (must pick an allowed
  state to enter), "Your pools" + "Open pools" grids of `SoloPoolCard`s. Each
  card shows the qualifying standard, entry/pool/rake/max-prize, a Join → Confirm
  flow, and for your OPEN pools demo **"I cleared it" / "I missed"** buttons.
  Settled cards show payout + clearer count + your detail line.
- **Tournaments**: page header, `GameTabs`, Region bar, "Your tournaments" +
  "Open tournaments" grids of `TournamentCard`s. Cards show format
  (leaderboard vs single-elim bracket), ranking metric or "draws rematch",
  prize split, entrants `n/max`, entry/pool/rake. Your OPEN tournaments get a
  **"Play & settle tournament"** button; settled cards render **final standings**
  (top 6, crown on #1, your row highlighted) and, for brackets, a **round-by-round
  played-out bracket** (winners bolded in emerald, rematch/bye details).
- **Leaderboard**: a `.data-table` ranked by **ROI** with columns #, Player,
  Contests, Record, Win rate, ROI, Net. The signed-in user is merged in (once
  they've played a graded contest) and highlighted as "You". Bots are flagged.
- **Active Matches**: `ActiveContractCard`s with a live countdown, objective,
  entry, "Win to take" prize, a **"Go play"** deep-link (Lichess hooks for chess;
  a non-link placeholder for CS2/Dota), and a **"Watch live game"** toggle that
  opens the **SpectatorPanel** (chess move list + clocks) or **MatchTrackerPanel**
  (CS2/Dota latest-match summary).
- **Profile** (the hub): the full **Link Accounts** grid (per-game cards — chess
  via Lichess; CS2 via FaceIt; Dota via OpenDota with a Steam32-ID hint; Clash
  Royale / Rocket League locked), then a **chess skill card** (when linked, with
  per-format ratings), the **Wallet** breakdown, and **My Contests** (P&L history
  table + per-opponent head-to-head records).
- **Responsible Gaming**: a daily-loss-limit slider ($0–$500, step $25, persisted)
  and a self-exclusion **stub** (toast only).

---

## 10. Backend (FastAPI, `api/`)

Stateless serverless functions under `/api`. CORS allows the Vite dev origins.
`app = FastAPI(title="money match API", version="2.0.0")`.

### Routes (`api/index.py`)
| Method & path | Purpose | Status |
|---|---|---|
| `GET /api/health` | service + registered game ids | works |
| `GET /api/profile?username=&game=` | link/refresh a `SkillProfile` (404 if not found, 502 on host error) | works (chess/dota keyless; CS2 needs key) |
| `GET /api/lobby?username=&game=` | generated OPEN H2H lobby for the user | works |
| `POST /api/contracts/price?username=` | build one Builder draft → matched OPEN `Contract` | works |
| `POST /api/contracts/settle` | grade in-flight contracts vs real games, grouped by (game, account) | works |
| `GET /api/solo/lobby` | seeded OPEN solo pools (with bot entrants) | works |
| `POST /api/solo/pools` | create a pool | works (not called by the UI) |
| `POST /api/solo/pools/enter` | escrow an entry — **geo-fence before charge** (403 if blocked) | works |
| `POST /api/solo/pools/settle` | grade telemetry + distribute pool | works |
| `GET /api/tournaments/lobby` | seeded OPEN tournaments (bots, one seat open) | works |
| `POST /api/tournaments` | create a tournament | works (not called by the UI) |
| `POST /api/tournaments/enter` | escrow entry (403 region, 409 full) | works |
| `POST /api/tournaments/settle` | rank + distribute (leaderboard or bracket) | works |
| `GET /api/leaderboard` | seeded ROI-ranked bot field | works |
| `GET /api/spectate?username=` | live Lichess current-game move list/clocks | works (chess) |
| `GET /api/track?game=&username=` | latest CS2/Dota match summary | works (CS2 needs key) |
| `GET /api/dev/faceit/{matches,distribution,telemetry}` | **dev-only** CS2 inspection; 404 in prod (Vercel guard) | works in dev |

### Lobby & matchmaking
- `lobby.build_contract(profile, draft)` matches an opponent + computes the
  bracket and pot/prize/rake. Opponent source is per-game: chess uses the
  per-time-control rating (±80 band), CS2 uses FaceIt elo (±150), Dota uses MMR
  (±800).
- `lobby.generate(profile)` produces a varied lobby: ~8 chess contests across the
  top two time controls/entry tiers mixing win-the-match and win-under-moves; for
  CS2/Dota, a set of "win your next match" contests across entry tiers.
- Rake: `win_h2h` 8%, `win_under_moves` 12%, default 10% (`skill_rating.rake_for`).
- `matchmaking.can_pair` is an **anti-collusion stub** (rejects self-pairing /
  repeats) — the seam for production checks.

### Adapters (the game-agnostic seam)
`GameAdapter` ABC (`link_account`, `fetch_profile`, `poll_eligible_games`,
`resolve_contract`) produces host-agnostic `NormGame`s so settlement never sees
host JSON. `registry.py` registers **three**: `chess.lichess`, `cs2.faceit`,
`dota2.opendota`. `stub_cs2.py` (`cs2.steam`) is an unregistered throwaway that
raises if called.

- **Chess (Lichess, no key):** profile from `/api/user/{u}` (perfs → formats,
  win/draw rates, primary speed). Settlement polls `/api/games/user/{u}` (NDJSON,
  rated, `moves=true`), grades the **first qualifying game since `matched_at`**
  (same speed, rated): `win_h2h` = won; `win_under_moves` = won AND under N full
  moves; window expiry with no game → CANCELED + refund. Verifies the linked user
  is actually a player in each game.
- **CS2 (FaceIt, key required):** profile from `/players?nickname=` + lifetime
  stats; **rejects legacy CS:GO-only accounts** with a clear 404. Settlement
  resolves the nickname → player_id, fetches match history, grades the **first
  finished match since `matched_at`** (win/loss from faction vs `results.winner`).
  It also enriches each match with per-player telemetry (`Kills/Deaths/K-D/HS%/
  ADR/MVPs`) used for CS2 solo grading and the Lab; `norm_to_telemetry` converts
  a match to a `TelemetrySample`.
- **Dota 2 (OpenDota, no key):** accepts a numeric Steam32 id directly, or
  searches a persona name and tries candidates (many profiles are private).
  Profile from `/players/{id}` + `/wl` (+ rank-tier → medal label, MMR estimate
  fallback). Settlement grades the first finished recent match
  (`player_slot` vs `radiant_win`).

### Solo engine (`solo_challenge.py`)
- **Geo-fence first**: `assert_can_enter(state)` raises `RegionBlockedError`
  (→ 403) for the 14 restricted states *before* an entry is escrowed. Idempotent
  per player.
- Pools are seeded with bot entrants across all five games so they're joinable.
- `grade_entry` checks (possibly compound) telemetry; missing/mismatched → `None`
  = refund, never a "failure".
- `settle_pool` invariant **`sum(payouts) + rake == sum(entries)`** in every
  branch: under min entrants → CANCELED + full refund, zero rake; no clearers →
  SETTLED + full refund, zero rake; ≥1 clearer → un-verifiable refunded off the
  top, rest raked and split equally among clearers.

### Tournament engine (`tournament.py`)
Generalizes the solo engine to ranked top-N. Same geo-fence-first + rake-only +
invariant rules. `leaderboard_pool` ranks by the metric directly; `single_elim`
**plays out a real bracket**: standard seeding, byes to top seeds, a per-game
favored-but-not-deterministic model (`_FAVORED_WEIGHT=0.8`), draws (`_DRAW_PROB
=0.15`) force a rematch (capped at 12 games), then derives a full finish order.
Prize split is renormalized if fewer ranked finishers than paid places.

### Leaderboard / spectate / tracker
- `leaderboard.generate_leaderboard()` — deterministic (fixed seed) bot field,
  ROI-ranked. The client merges in the user's own record and re-ranks.
- `spectate.parse_current_game` / `tracker.parse_faceit|parse_dota` — pure
  parsers; the route does the fetch.

---

## 11. Desktop overlay (Electron) — **legacy, not wired**

A separate transparent, always-on-top `BrowserWindow` that sits above a
borderless-windowed game.

- **`electron/main.ts`** builds the overlay (`transparent`, `frame:false`,
  `alwaysOnTop`, `focusable:false`, `setAlwaysOnTop(...,'screen-saver')`,
  `setIgnoreMouseEvents(true,{forward:true})`), loads `?electron=1`, and wires
  the detector (focus → resize + `showInactive`; move → reposition; blur → hide).
  IPC: `overlay:clickThrough` toggles pass-through; `overlay:openContract` opens
  the web app — **hardcoded to `https://clutchbook.app` in prod** (legacy URL).
- **`detector/`** — `PollingDetector` (`get-windows` every 750ms, DENY→ALLOW→
  85%-area heuristic, DPI fix) and `MockDetector` (hotkey-driven). Factory keys
  off `OVERLAY_MOCK=1`.
- **`ContractOverlay.tsx`** — a polished tab↔card Framer-Motion widget.

> **The overlay still uses the pre-pivot odds model.** Its content shape
> (`ContractContent` in `types/overlay.ts`) has `line` / `fairLine` /
> `houseEdgePct` / `payout`, and `getWagerForGame()` returns a **single static
> `DEMO_CONTENT`** ("house edge 7.5%") for every game. It is **not connected** to
> the peer-to-peer/pooled backend, the wallet, or the real contract shapes. Treat
> it as a standalone visual demo that contradicts the no-house product model.

---

## 12. Tests

Backend `pytest` suites exist (`/tests`, with `conftest.py` adding `api/` to the
path):
- **`test_tournament.py`** — the escrow/rake invariant on every settlement path
  (leaderboard + bracket), refunds, prize-split renormalization.
- **`test_surfaces.py`** — leaderboard ROI ordering/determinism + self-consistency;
  spectator and tracker pure parsing.
- **`test_faceit.py`**, **`test_dota.py`** — adapter/service parsing & normalization.

There are **no frontend tests** and no React component tests. `npm run lint` is a
type-check only (`tsc --noEmit`).

---

## 13. What works vs. mocked vs. not wired (the honest summary)

### Works end-to-end (backend running; CS2 also needs `FACEIT_API_KEY`)
- Linking a **real Chess (Lichess)**, **CS2 (FaceIt)**, or **Dota 2 (OpenDota)**
  account — real ratings/stats; three independent linked identities at once.
- Personalized **H2H lobby** + the Builder's **live matchmaking preview** for all
  three live games.
- **Joining a contract** (escrow), the 15s settlement poll, and **real grading
  against the user's actual recent games** on all three live games (win/loss/
  refund + wallet + toast). Multi-game contracts settle through the right adapter.
- **Solo pools**: join (geo-fenced), settle, correct pool distribution math
  (invariant holds). CS2 solo grades the player's entry against their **real
  latest FaceIt match**; other games use the demo clear/miss button. Bots mocked.
- **Tournaments**: join (geo-fenced, full-field 409), settle, leaderboard + a
  fully played-out single-elim bracket, correct payout math.
- **Leaderboard** (ROI-ranked, user merged in), **chess spectator** (live move
  list/clocks from Lichess), **CS2/Dota match tracker**.
- **FaceIt Lab** (`?lab=faceit`) — real CS2 profile, recent-match table, metric
  distribution, and a (illustrative) resolution simulation.
- Wallet, geo-fence gate (client + server), contest history & P&L, profile.

### Mocked / demo-only
- **All opponents are bots** — no real second player, no real matchmaking queue.
- **Solo telemetry** is fabricated client-side (`genTelemetry`), **except** CS2
  which can use real FaceIt telemetry. **Tournament telemetry/scores are entirely
  mocked** (`genScore`). Bots clear at ~55%.
- **Play money only** — no deposits/KYC/withdrawals; `locked` wallet bucket unused.
- Client owns contract/pool/tournament/wallet state; **no DB**; settlement poll
  is client-driven.
- Leaderboard competitors are a **seeded bot field**.
- Auth is a **mock gate** (the Landing eligibility check); no real accounts.

### Built but NOT wired into the app
- **The Electron overlay** — runs, but uses the legacy odds shape and static demo
  content; not connected to the real backend/wallet (§11).
- **`useContracts.lobby` / `refreshLobby`** — fetched but **not rendered**; the
  Lobby tab fetches its own per-game lobby directly (§14).
- **`Sparkline`** component (and `recharts`) — present but rendered nowhere.
- **`POST /api/solo/pools` and `POST /api/tournaments`** (create endpoints) — exist
  and tested but the UI never calls them (lobbies are server-seeded).
- **OAuth linking** — the code path exists (`link_method` switch) but only the
  username/public path is used.
- **Clash Royale & Rocket League** — UI "coming soon" only; no adapters.

---

## 14. Known rough edges / honesty notes

These are real things a reader/QA should know:

1. **Daily loss limit isn't actually enforced.** `useWallet.canJoin` returns
   `entry > 0 && entry <= available && entry <= remainingLoss + available`. Since
   `remainingLoss >= 0`, the third clause is always implied by the second, so
   hitting the loss limit does **not** block joining. The slider persists and the
   "remaining" text updates, but the cap is effectively cosmetic. The
   Responsible-Gaming "Daily loss limit reached" toast in `handleJoin` is
   therefore essentially unreachable.
2. **Two lobby fetchers.** `useContracts` fetches a chess-only lobby on mount
   (and exposes `refreshLobby`), but the rendered **Lobby** tab (`GameLobby`)
   fetches its own per-game lobby via `fetchLobby` directly. The `useContracts`
   lobby is dead for display purposes — minor wasted request + confusion risk.
3. **Overlay contradicts the product.** It still shows a house edge / odds line
   and points at `clutchbook.app` (§11). If shown to anyone, clarify it's legacy.
4. **CS2 hard-depends on a FaceIt key.** Without `FACEIT_API_KEY`, CS2 linking,
   lobby, settlement, tracker, and the Lab all fail (404/empty). Chess and Dota
   work with no key.
5. **FaceIt Lab "Simulate Resolution"** prints `+$9.00 net (90% rake)` — the
   label text is misleading (it's an illustrative hardcoded number, not a real
   90% rake). Dev-only surface, no wallet impact.
6. **No real data webhook.** Solo/tournament grading is designed around a
   "telemetry webhook" that doesn't exist; the demo synthesizes telemetry
   (except CS2 solo, which reads real FaceIt stats).
7. **`requirements-dev.txt`** exists alongside `requirements.txt`; the README is a
   single line ("# money match"), so run instructions live here, not in the README.
8. **Geo-fence list must stay in sync** in two places: `src/utils/states.ts`
   `EXCLUDED_STATES` (14) and `api/_lib/solo_challenge.py` `RESTRICTED_STATES`
   (14). They currently match.

---

## 15. State persistence (localStorage)

All keys prefixed `moneymatch:` (`utils/storage.ts`):
`started`, `residence`, `profile` (chess), `faceit_profile`, `dota_profile`,
`wallet`, `contests`, `solo_pools`, `tournaments`, `game_selected`, `game_order`.
**Reset balance** clears `contests`, `solo_pools`, `tournaments`, and the wallet
(it does **not** unlink accounts). The backend stores nothing (besides FaceIt's
in-process match-stats cache).

---

## 16. Conventions for making changes

- **No odds/lines on user-facing surfaces.** The product is rake-only,
  peer-to-peer/pooled. Don't reintroduce house pricing (the overlay is the lone
  legacy exception and should eventually be migrated).
- **Schema parity:** change a shape in `api/_lib/schemas.py` *and*
  `src/types/index.ts` together.
- **Geo lists parity:** `states.ts EXCLUDED_STATES` ↔
  `solo_challenge.RESTRICTED_STATES` (14 full state names).
- **Money invariants:** H2H `payout(winner) + rake == pot`; solo & tournaments
  `sum(payouts) + rake == sum(entries)`. The pytest suite guards the pooled ones.
- **Adapters, not imports:** resolve games via `registry.get(id)`; settlement
  works on `NormGame`, never host JSON.
- **Currency formatting** comes from `src/utils/format.ts` (`formatCurrency`,
  `formatPct`). There is no odds formatter.
- **Telemetry event names** (`utils/telemetry.ts`) are meant to outlast the demo —
  keep them stable (in the demo `track` only `console.debug`s in dev).
- Tailwind is for layout only; colors/typography/surfaces come from the CSS
  tokens in `src/index.css`.
