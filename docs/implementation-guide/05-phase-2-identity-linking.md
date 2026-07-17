# Phase 2 — Identity & Game Linking (Adapters)

**Objective:** port the PoC's game adapters (the platform's core asset) into the
new service, bind host-game accounts to users with immutable server-side links,
and ship the Profile screen. After this phase, "FACEIT/data extraction works."

**Depends on:** Phase 0 (parallel with Phase 1). **Unblocks:** Phase 3.

---

## Deliverables

1. **Adapter layer ported** to `apps/api/src/moneymatch_api/adapters/`:
   - `base.py` — `GameAdapter` ABC + `NormGame`, `GameFilters`, `TelemetrySample`
     value types (port from `poc-reference/api/_lib/adapters/base.py`).
   - `chess_lichess.py`, `cs2_faceit.py`, `dota2_opendota.py` + the three
     service clients (`lichess_service`, `faceit_service`, `opendota_service`).
   - `registry.py` — id → adapter, filtered by feature flags.
   - Port changes (do during the port, not after):
     * async httpx clients with explicit timeouts + retry (tenacity, 2 retries,
       jittered) and typed upstream errors (`HostUnavailable`, `HostNotFound`);
     * FaceIt in-process cache → small TTL cache keyed by match id (fine for
       one process; worker and api each have their own);
     * CS:GO-legacy rejection, Dota Steam32-id handling, private-profile
       detection kept exactly as PoC (they encode hard-won edge cases);
     * **Dota expose-data gate at link time** (launch plan §6.1): verify recent
       matches are actually readable via OpenDota; if "Expose Public Match
       Data" is off, block the link with instructions — never a silent
       settlement failure later;
     * **raw payload retention**: every host response that will feed a grading
       or profile decision is persisted to `raw_payloads` and referenced from
       the derived record (audit requirement — see `01-architecture.md` §2);
     * every adapter method logs host latency (structlog) for ops.
2. Migration + service for **`linked_accounts`** (unique `(user_id, game)` and
   `(game, host_account_id)` — one host account per platform user, DB-enforced).
3. Endpoints: `GET /links`, `POST /links {game, username}` (server fetches the
   profile via the adapter, verifies existence, stores snapshot, binds),
   `GET /links/{game}/profile` (refresh snapshot), `DELETE /links/{game}`
   (admin-only in MVP — bindings are immutable to users).
4. **Profile screen** (PDF p.12): avatar/username/member-since, Linked games
   rows with LINKED/BLOCKED status (BLOCKED = feature-flag-disabled game or
   frozen binding), link flow (row → username input → server verify → LINKED),
   Limits rows (read from Phase 1), Self-exclude action (red).
5. Onboarding step 3 ("link your first game") wired to the same link flow.
6. **Metric-model bootstrap** (`metric_models` — see `01-architecture.md` §2):
   on link, pull the account's recent match history (last ~50 matches; keep the
   raw payloads) and compute per-metric `mu`/`sigma`/`n` with recency weighting
   (EWMA, half-life 10). Refresh hooks fire on settlement (Phase 3) and
   nightly. **Provisional floors** (from the challenge-engine proposal §3/§6):
   `n < 10` on a metric ⇒ no stat duels/pools on that metric; accounts below a
   per-game history floor (e.g. 20 rated chess games / 25 FaceIt matches) get
   H2H `win` markets only. Floors live in config, not code.
7. `GET /health` reports registered games from the registry + flags.

## OAuth posture (MVP decision)

Username-claim linking ships at MVP (fastest path; internal-team testing).
**OAuth is the very next step after MVP** (Lichess OAuth + FaceIt OAuth2 +
Steam OpenID) because username-claim lets anyone bind anyone's account
(`docs/legal/integrity-audit.md` #5). Requirements *now* so OAuth drops in later:

- `link_method` column exists (`username|oauth`);
- linking flows through one `linking_service.bind(user, game, evidence)` seam;
- settlement (Phase 3) verifies the bound account actually played the graded
  game — the adapter checks already do this; keep them.

## Reuse from `poc-reference/` (this phase is mostly a port)

| What | From | Change |
| --- | --- | --- |
| Adapter ABC + value types | `api/_lib/adapters/base.py` | as-is + `TelemetrySample` moves here |
| Lichess adapter/service | `api/_lib/adapters/chess_lichess.py`, `_lib/lichess_service.py` | async + retries |
| FaceIt adapter/service | `api/_lib/adapters/cs2_faceit.py`, `_lib/faceit_service.py` | async + TTL cache; keep telemetry enrichment (`norm_to_telemetry`) |
| OpenDota adapter/service | `api/_lib/adapters/dota2_opendota.py`, `_lib/opendota_service.py` | async; keep private-profile candidate search |
| Registry | `api/_lib/adapters/registry.py` | + feature-flag filter; drop `stub_cs2.py` |
| SkillProfile shape | `api/_lib/schemas.py` (SkillProfile, FormatStat) | becomes the `profile_snapshot` schema |
| Adapter/service tests | `tests/test_faceit.py`, `tests/test_dota.py` | port to pytest-asyncio + respx fixtures |

## Tests required

- Ported PoC parsing/normalization suites green against recorded fixtures
  (respx-mocked; **no live host calls in CI**).
- Linking: unknown username → 404; already-bound host account → 409; second
  game links independently; profile snapshot refresh updates fields.
- Uniqueness: two users racing to bind the same host account — exactly one wins
  (DB constraint, not app check).
- Adapter resilience: host 5xx → typed error → API returns 502 with clean body;
  timeout path covered.

## Exit criteria

- [ ] Real Lichess, FaceIt, and OpenDota accounts link end-to-end in the UI and
      show correct ratings/stats on Profile (FaceIt requires `FACEIT_API_KEY`).
- [ ] A second user cannot bind an already-bound host account.
- [ ] CI green with zero network access (all host APIs fixture-mocked).
- [ ] Disabling a game flag hides it from linking and marks it BLOCKED on Profile.
