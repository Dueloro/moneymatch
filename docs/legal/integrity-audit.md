# Integrity & Anti-Abuse Audit (code-verified)

**Last updated:** 2026-07-15 (migrated from the PoC repo `clutchbook`)
**Scope:** how easy it was, *in the PoC code*, to fake results, forge money, field bots/smurfs, or collude — and what has to change at each launch stage. File references are to the PoC layout and resolve under [`/poc-reference`](../../poc-reference/) in this repo.

> **Migration note.** This audit is the reason the MVP architecture is
> server-authoritative. Vulnerabilities #1–#5 and #10 are designed out by the
> [implementation guide](../implementation-guide/00-README.md) (Phases 0–3);
> the per-stage exit tests in §7 remain the release gates. The legacy Electron
> overlay (#12) was **not migrated** to this repo.

> This is an audit of a **play-money demo**, so none of these are live incidents. They matter because (a) the gems launch makes forgeable state worth stealing, and (b) investors and payment processors will diligence exactly these seams. Severity is rated for the *gems* phase; everything red must be fixed before gems, everything at all before money.

---

## 1. Threat-model summary

| # | Vulnerability | Where | Severity (gems) | Fix stage |
| --- | --- | --- | --- | --- |
| 1 | Wallet & all contest state is client-owned localStorage — trivially editable | `src/hooks/useWallet.ts`, `utils/storage.ts` | 🔴 Critical | No-money MVP |
| 2 | Settlement endpoints trust client-supplied contract objects (entry/pot/prize/`matched_at`) | `POST /api/contracts/settle`, `api/index.py` | 🔴 Critical | No-money MVP |
| 3 | Solo/tournament telemetry is **self-reported** ("I cleared it" buttons; client-posted scores) | `SoloPoolCard.tsx:112`, `useSoloPools.ts:107`, `useTournaments.ts:81`, `api/index.py:208,257` | 🔴 Critical | No-money MVP |
| 4 | No authentication — identities are client-chosen strings | `Landing.tsx` mock gate; `player_id` in `match_queue.py` | 🔴 Critical | No-money MVP |
| 5 | Account linking is unverified username-claim (link anyone's Lichess/FaceIt/Steam account) | `useProfile.ts`, `GET /api/profile` | 🔴 Critical | No-money MVP |
| 6 | Brokered chess URLs are open challenges — anyone with the link (a hired ringer) can take the seat | Phase-1 flow, `match_queue.py` + Lichess open challenge | 🟠 High | Gems |
| 7 | Smurfing/sandbagging: no account-age/games-played floors; band widens to ±800 | `match_queue.py:39`, `lobby.py` | 🟠 High | Gems |
| 8 | Collusion controls are a stub (`can_pair` only rejects self/repeat by client-set id) | `api/_lib/matchmaking.py:99` | 🟠 High | Gems |
| 9 | Geo-fence is a self-selected dropdown, mirrored client+server but attestation-only | `states.ts`, `solo_challenge.assert_can_enter` | 🟡 Medium (🔴 at money) | Money |
| 10 | Loss limit not enforced (`canJoin` tautology) | `useWallet.ts` | 🟡 Medium (🔴 at money) | No-money MVP (it's a one-line fix) |
| 11 | Dota private profiles / delayed data break or spoof settlement windows | `opendota_service.py` | 🟡 Medium | Gems |
| 12 | Legacy Electron overlay shows house-edge odds — contradicts the legal story if ever shown | `electron/`, `getWagerForGame.ts` | 🟡 Reputational | Delete or migrate |

---

## 2. Score verification: what's real and what's self-reported

**Head-to-head is genuinely host-authoritative — the good news.** Chess/CS2/Dota H2H settlement reads finished games from Lichess/FaceIt/OpenDota and grades server-side (`api/_lib/adapters/*`). The client never says "I won." This is the platform's core differentiator and it already works.

**Everything else currently self-reports:**

- **Solo pools:** the UI literally has **"I cleared it / I missed"** buttons (`SoloPoolCard.tsx:112`); the client fabricates telemetry (`genTelemetry`) and posts it to `POST /api/solo/pools/settle`, which grades whatever it's told (`api/index.py:208` — the route docstring calls itself a "mock telemetry webhook"). Even the CS2 "real telemetry" path fetches FaceIt stats *client-side* and posts them — a self-report with extra steps, since the payload can be edited in flight.
- **Tournaments:** every entrant's score is client-generated (`genScore`, with a "strong bias" for the human) and posted to `POST /api/tournaments/settle`.
- **H2H money math:** `POST /api/contracts/settle` receives the whole `Contract` from the client — `entry`, `pot`, `prize`, `rake_pct`, `matched_at`, `account_id` are all attacker-controlled. A tampered client can claim a $1,000 pot on a $1 contest, or set `matched_at` in the past to capture a game it already won.

**The fix is one architectural rule, applied in the no-money MVP:** *the server owns every number.* Contracts are created and stored server-side; settle requests carry only an id; telemetry is fetched by the **server** from the host API (or a real webhook), never accepted from the client. This converts vulnerabilities #1–#3 into non-issues in one move, and it's the prerequisite for the roadmap's Phase 2 ledger anyway.

---

## 3. Faking matches and results per game

- **Chess (brokered open challenge):** the server creates a Lichess *open* challenge and hands each player a color URL. Nothing binds the URL to the queued human — **a player can hand their link to a 2400-rated friend** (ringing). Mitigation: require Lichess OAuth account linking before real matchmaking, create the challenge *targeted at the two linked accounts* (Lichess supports direct challenges via OAuth), and verify at settlement that the game's players are exactly the two bound accounts (the adapter already checks the linked user played — extend to both sides).
- **CS2/Dota (coordinated):** settlement finds the shared match between the two linked accounts — solid *if* account binding is real (vuln #5). With username-claim linking, I can "link" a pro's FaceIt account and queue with their elo. OAuth (FaceIt supports OAuth2) / Steam OpenID binding closes this.
- **Replay/duplicate capture:** settlement grades "first qualifying game since `matched_at`" — with client-set `matched_at` (vuln #2) any historical win can be claimed. Server-owned timestamps fix it.
- **Screenshots:** we don't use them — keep it that way. The moment a title requires screenshot/OCR verification (the `docs/old` computer-vision pipeline), we inherit Players' Lounge's dispute-moderation cost center and its fraud rate. Host-API-verifiable titles only.

---

## 4. Bots, smurfs, and multi-accounting

Skill-based platforms are farmed the way ranked ladders are, plus a financial incentive. Current exposure:

- **No identity cost:** no auth (vuln #4) → unlimited free accounts; one human can hold both sides of a queue (self-collusion). `can_pair` rejects same-`player_id` pairs, but ids are client-chosen strings.
- **No skill-history floor:** a fresh Lichess account with 10 games has a provisional, sandbagg-able rating; we accept it straight into bracketing (`lobby.py` reads the host rating as-is; `FormatStat.provisional` exists in the schema but isn't used as a gate).
- **Band widening to ±800** (`match_queue.py:39`) will eventually pair a sandbagger with a genuine novice — good for liquidity metrics, terrible for integrity and new-player retention.

**Controls to build (gems phase, the roadmap's Phase 4 track):**
1. Real auth + one-account-per-human signals: email+device fingerprint at gems; KYC dedup at money.
2. Host-account floors before rated contests: minimum account age, minimum rated games (e.g. 50), non-provisional rating; per-adapter thresholds.
3. Rating-integrity checks: compare performance in our contests vs. host rating; flag over-performers (sandbaggers) for bracket correction, not punishment.
4. Immutable account binding (already the stated policy in `overview.md` §5 — enforce it in code once bindings are server-side).
5. Cap band widening for contests that matter; let *wait time*, not mismatch, absorb thin liquidity, and use clearly-labeled bots only in play-money warmup queues (already the roadmap's rule).

---

## 5. Collusion & laundering (the model's structural risk)

Because we layer on games we don't control, two accounts can agree on an outcome. With gems non-transferable (see [`legal-compliance.md`](./legal-compliance.md) §6.2), gem-phase collusion is mostly leaderboard fraud; at money it becomes theft/laundering.

Build order (maps to roadmap Phase 4):
1. **Pair-frequency limits** — the `can_pair` seam exists (`matchmaking.py:99`); make it stateful (server-side pair history) and enforce cooldowns.
2. **Clustering** — device fingerprint, IP/ASN, (at money) payment-instrument graph; block intra-cluster pairing.
3. **Directional value-flow detection** — flag pairs whose lifetime net flows one way beyond a threshold; at money this doubles as the AML monitoring processors require.
4. **Host cheat-flag ingestion + clawback** — Lichess marks cheaters; poll flags post-settlement and claw back per the user agreement (needs the Phase 2 ledger to reverse cleanly).
5. **Ops surface** — the risk view (flag queue, account freeze, pair-block) so a human can act without a deploy.

---

## 6. API dependencies vs. developer ToS (product-side view)

Full legal analysis in [`legal-compliance.md`](./legal-compliance.md) §2; the engineering consequences:

| Dependency | Used for | Risk & engineering hedge |
| --- | --- | --- |
| Lichess public API (no key) | Profile, games, spectate, **open-challenge brokering** | Low today; get their blessing before scale. Hedge: `GameAdapter` seam means a Chess.com adapter is a bounded task. |
| FaceIt Data API (key, free tier) | CS2 profile/matches/telemetry | Dev-portal terms not publicly readable; free tier is presumptively non-commercial. Hedge: budget for FaceIt partner terms or GRID before money. |
| OpenDota (no key) | Dota profile/matches | Community API over Valve's data; fine for demo, not a money-grade foundation (rate limits, private profiles, Valve's anti-gambling posture). Hedge: GRID/PandaScore enterprise at Stage C, or drop Dota. |
| Vercel serverless + in-memory state | Matchmaking queue, FaceIt cache | Not a ToS issue but an integrity one: in-memory queue (`match_queue.py`) loses matches on cold start — escrowed entries could strand. Postgres/Redis in the no-money MVP. |
| Electron overlay (`get-windows`) | Legacy demo | Displays house-edge odds contradicting the no-house model; points at `clutchbook.app`. **Delete or quarantine before anyone external sees it.** |

---

## 7. What "integrity-complete" looks like per stage

- **No-money MVP:** server-authoritative state and money math (#1, #2, #3, #10); real auth (#4); OAuth-grade account binding (#5). *Exit test: a tampered client cannot change any settled amount.*
- **Gems launch:** targeted challenges bound to accounts (#6); smurf floors (#7); pair-frequency + device clustering (#8); Dota privacy handling (#11). *Exit test: a two-account self-play attempt is blocked; a thrown-game pair gets flagged.*
- **Money launch:** GPS geolocation (#9); payment-instrument clustering; clawback; AML velocity rules; risk-ops console. *Exit test: the fraud playbook (ringer, sandbagger, colluding pair, launderer) runs against staging and every scenario is caught or bounded.*
