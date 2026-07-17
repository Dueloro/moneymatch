# PoC → MVP Migration Map

What to reuse from the PoC, where it lives, and what changes during the port.
The PoC code is mirrored read-only in [`/poc-reference`](../../poc-reference/)
(original repo: `~/Desktop/clutchbook`). Ground truth for how the PoC behaves:
[`poc-reference/POC-IMPLEMENTATION.md`](../../poc-reference/POC-IMPLEMENTATION.md).

**Porting rules:** port with tests (the PoC test suites move first and become
the spec); floats → integer cents everywhere; client-supplied values → server-owned;
never `import` from `poc-reference/`.

---

## 1. Port nearly as-is (high-value, well-tested)

| PoC file | → MVP home | Phase | Notes |
| --- | --- | --- | --- |
| `api/_lib/adapters/base.py` | `adapters/base.py` | 2 | GameAdapter ABC + NormGame/GameFilters |
| `api/_lib/adapters/chess_lichess.py` | `adapters/chess_lichess.py` | 2 | async + retries |
| `api/_lib/adapters/cs2_faceit.py` | `adapters/cs2_faceit.py` | 2 | keep `norm_to_telemetry`, CS:GO-legacy rejection |
| `api/_lib/adapters/dota2_opendota.py` | `adapters/dota2_opendota.py` | 2 | keep Steam32/private-profile handling |
| `api/_lib/adapters/registry.py` | `adapters/registry.py` | 2 | + feature-flag filter |
| `api/_lib/lichess_service.py` | `services/hosts/lichess.py` | 2 | async httpx |
| `api/_lib/faceit_service.py` | `services/hosts/faceit.py` | 2 | async + TTL cache |
| `api/_lib/opendota_service.py` | `services/hosts/opendota.py` | 2 | async |
| `api/_lib/skill_rating.py` | `services/skill_rating.py` | 3 | rake config, Elo expectancy, bracket labels |
| `api/_lib/match_queue.py` | `services/matchmaking.py` | 3 | in-memory dicts → Postgres tables; keep pairing/lifecycle logic |
| `api/_lib/solo_challenge.py` | `services/pool_engine.py` | 4 | drop bot seeding + client telemetry |
| `api/_lib/tournament.py` | `services/tournament_engine.py` | 4 | leaderboard paths only; drop bracket sim |
| `api/_lib/leaderboard.py` | `services/leaderboard.py` | 5 | real users from ledger, not seeded bots |
| `tests/test_faceit.py`, `test_dota.py` | api tests | 2 | respx fixtures |
| `tests/test_matchmaking.py` | api tests | 3 | against DB-backed service |
| `tests/test_tournament.py` | api tests | 4 | **the settlement invariant spec** — port fully |
| `tests/test_surfaces.py` | api tests | 4/5 | leaderboard + parser portions |

## 2. Reuse the shape/logic, rewrite the substrate

| PoC source | What survives | Phase |
| --- | --- | --- |
| `api/_lib/schemas.py` | Field vocabulary for the new SQLAlchemy models + Pydantic schemas (Contract→Match, SoloPool, Tournament, SkillProfile, MetricTarget, Bracket) | 1–4 |
| `api/index.py` | Route inventory + Lichess challenge-brokering flow + FaceIt distribution route (→ tier seeder) | 2–4 |
| `frontend/src/hooks/*` | Polling cadences, optimistic-UI and state patterns → TanStack Query hooks | 3–5 |
| `frontend/src/utils/format.ts` | Currency/pct formatting → cents-based | 1 |
| `frontend/src/utils/telemetry.ts` | The 12 stable event names → PostHog | 6 |
| `frontend/src/utils/states.ts` | 14-state exclusion list → `geo_config` seed | 0 |
| `frontend/src/utils/games.ts`, `playerStats.ts`, `contractText.ts`, `soloText.ts`, `tournamentText.ts`, `recommend.ts` | Copy/derivation helpers — mine for logic as screens are built | 3–5 |
| `frontend/src/index.css` | Token architecture (not values — new palette per design PDF) | 0 |
| `tests/../conftest.py` | pytest path/fixture setup pattern | 0 |

## 2b. Specified but never committed (build fresh from the proposals)

The [production launch plan](../proposals/production-launch-plan-v3.md)
references an `api/_lib/demo/` module (`demo/ledger.py` double-entry ledger,
`demo/matcher.py` SkillMatcher, `demo/store.py`, `demo/routes.py`). **That code
was never committed to the PoC repo** (verified across all branches) — it is
not in `poc-reference/`. The concepts are implemented fresh: the ledger by
Phase 1 (`wallet_service` + `ledger_entries`), the skill/metric models and
matcher by Phases 2–4 (`metric_models`, duel-forecast pairing, room formation),
from the specs in the proposal docs.

## 3. Do NOT migrate (deliberate)

| PoC piece | Why |
| --- | --- |
| Electron overlay (`electron/`, `ElectronApp.tsx`, `getWagerForGame.ts`, `types/overlay.ts`) | Legacy house-edge/odds model — contradicts the product's legal frame (`docs/legal/integrity-audit.md` #12). Left in the PoC repo; `overlay.ts` in poc-reference is inert. |
| localStorage state (`storage.ts` persistence model, `useWallet` client money) | Server owns every number now |
| "I cleared it / I missed" buttons, `genTelemetry`, `genScore` | Self-reporting is banned (integrity #3) |
| Bot opponents & seeded bot leaderboard/pools | Real users only; honest empty states |
| Client-posted settle bodies (`POST /api/contracts/settle` etc.) | Settle-by-worker only |
| `stub_cs2.py` | Dead stub |
| Rocket League / Clash Royale surfaces, `sampleContracts.ts` previews | Publisher-ToS dead ends (`docs/legal/legal-compliance.md` §2) |
| PoC visual design (lime tokens, 7-tab sidebar, card layouts) | Replaced by the design PDF |
| Vercel serverless single-file API shape | Long-running service + worker now |
| Chess spectate / CS2-Dota trackers (`spectate.py`, `tracker.py`, `useSpectate`, `useTrack`) | Nice-to-have, not MVP; parsers are tested — **backlog**, port later for the Activity detail view |

## 4. Known PoC bugs that must not survive the port

From `POC-IMPLEMENTATION.md` §14 / the integrity audit:

1. Loss-limit tautology (`useWallet.canJoin`) → server-side `assert_can_stake` (Phase 1).
2. Client-owned `matched_at` / contract math → server-owned (Phase 3).
3. Float money math (`_round2`) → integer cents (Phase 1).
4. Dual lobby fetchers / dead `useContracts.lobby` → one query per surface (Phase 3).
5. Geo list duplicated client+server → single `geo_config`, server-enforced (Phase 0/4).
6. In-memory queue losing state on restart → Postgres tickets (Phase 3).
