# Audit Findings

Findings from the production-hardening pass. Severity: **P0** blocks launch, **P1** fix before
real money, **P2** fix later.

Each finding gives a concrete failure scenario with inputs, not a description of a smell.

---

## P0-1 — The test suite never runs migrations, so no seed data is covered by any test

**Status:** root cause identified and enumerated; fix proposed below.
**Raised by:** `REPLY_TO_AGENT.md` §5, promoting a finding first noticed while fixing the
geo-fence.

### What is wrong

`tests/conftest.py` builds the test schema with `Base.metadata.create_all`. The Alembic chain
never runs in tests. Three consequences:

1. **No migration seed data exists in the test database.** Anything a migration `INSERT`s is
   invisible to every test.
2. **`create_all` can drift from the migration chain silently.** `alembic check` compares models
   to migrations; nothing compares *seeded rows*.
3. **A safety control that reads its configuration from a seeded row is untestable by
   construction** — it will read "unconfigured" in every test, forever.

### The failure scenario that already happened

The geo-fence reads its excluded-state list from the `geo_config` feature-flag row, seeded by
migration `0001`. In tests that row never existed, and `feature_flags.DEFAULT_FLAGS` has no
`geo_config` entry either. The old `geo_service.excluded_states` returned an empty set when the
row was absent, and an empty set excludes nobody.

**Every contest-entry test in the suite therefore passed through a geo-fence that was not
there.** No test could have caught a change that disabled the fence entirely, because no test
ever loaded a fence in the first place. That is how the fail-open bug reached production.

### The size of the hole — measured, not estimated

Produced by running the full migration chain into a scratch database and diffing its seeded state
against what the fixture produces.

**Tables holding rows after a clean migration:** `alembic_version` (1), `feature_flags` (8).
Seed data is confined to feature flags, which bounds the problem.

**Seeded by migrations, absent from the test fixture — 3:**

| Key | Seeded by | Payload | Consequence of absence in tests |
| --- | --- | --- | --- |
| `geo_config` | `0001` | the 14 excluded states | **The geo-fence was untested. This is P0-1's origin.** Fixed. |
| `worker_heartbeat` | `0007` | `{}` | Heartbeat-staleness behaviour diverges between test and production. |
| `game:cs2.faceit` | `0001` | `{}` | A retired game still carries an enabled flag row in production. |

**In the fixture but *not* seeded by any migration — 1:**

| Key | Consequence |
| --- | --- |
| `game:cs2.steam` | **See P1-1 below — this is a real production gap, not a test artefact.** |

**Payload drift:** the fixture writes `'{}'::jsonb` for every flag. Migration `0001` writes a
populated payload for `geo_config`. So even where a key matched, the *content* did not.

### Proposed fix — I would pick (a)

- **(a) Run the migration chain in the test fixture instead of `create_all`.** Eliminates the
  entire drift class: seed data, payloads, raw-SQL triggers and column defaults all become exactly
  what production has.
- **(b) Keep `create_all` and add a test asserting seeded state matches the migration chain.**
  Cheaper, but it is one more thing that can itself drift, and it only catches what it thinks to
  compare.

**Runtime cost of (a), measured:** `alembic upgrade head` against an empty database takes
**2.9 seconds**. The `_schema` fixture is session-scoped, so that is a one-time cost against a
**~11.5 minute** suite — about **0.4%**. That is comfortably tolerable, and it removes a whole
category of bug rather than one instance of it.

**Recommendation: (a).** With one caveat worth stating — running migrations makes the test schema
depend on the chain staying runnable from scratch, which is a *feature* (it continuously proves
the thing every deploy relies on) but will surface any migration that is not cleanly re-runnable.

---

## P1-1 — `game:cs2.steam` has no feature-flag row in production

**Found by:** the seed-diff above, as a side effect of P0-1.

`constants.REGISTERED_GAMES` includes `cs2.steam`, so `feature_flags.DEFAULT_FLAGS` derives a
`game:cs2.steam` entry — but **no migration ever inserts that row.** Migration `0020` seeded
`game:pubg.steam`; nothing did the equivalent when CS2 moved from FACEIT to Steam in `0024`.

**Why it is not currently breaking:** `get_boolean_flags` falls back to `DEFAULT_FLAGS` for keys
with no row, so CS2 reads as enabled, and `list_flags` synthesises a detached row so the admin UI
can still show and toggle it (the toggle upserts).

**The failure scenario:** the per-game kill switch for CS2 does not exist as a row until somebody
toggles it. If CS2 needs to be disabled in an incident — a Valve outage, a GC failure, a suspected
exploit — the operator is relying on a synthetic row being upserted correctly under pressure,
rather than flipping a row that is already there. Every other shipped game has a real row.

Meanwhile `game:cs2.faceit` **does** have an enabled row for a game that no longer exists. This is
visible on the deployed API today: `/api/v1/health` reports `"game:cs2.faceit": true`.

**Proposed fix:** a migration that inserts `game:cs2.steam` (enabled, `ON CONFLICT DO NOTHING`)
and removes `game:cs2.faceit`. Small, and it makes the flag table match the registry.

---

## P2-2 — Running alembic in-process silently disables existing loggers

**Found by:** implementing the P0-1 fix. Two tests in `test_secret_logging.py`
(`test_they_can_still_report_trouble[httpx]`, `[httpcore]`) began failing.

`migrations/env.py` calls `fileConfig(config.config_file_name)` whenever an ini path is set, and
`logging.config.fileConfig` defaults to **`disable_existing_loggers=True`**. So any in-process
`alembic upgrade` switches off every logger configured before it.

**Failure scenario beyond tests:** the API can run migrations in-process — `docker-entrypoint.sh`
runs them as a separate command today, so production is not currently affected. But anything that
imports alembic and upgrades inside a live process (a management command, a future in-app
migration step, a data backfill script) would silently lose `httpx`, `httpcore` and any other
already-configured logger for the remainder of that process. The symptom is *absence* of logs,
which is the hardest kind of failure to notice.

**Fixed in tests** by constructing `Config()` without the ini path, so env.py skips the logging
setup entirely (only `script_location` is needed; env.py sets the database URL itself).

**Recommended follow-up (not done here, outside this pass's scope):** make `env.py` pass
`disable_existing_loggers=False`, so the trap cannot catch a future caller. Left as a proposal
because `env.py` is shared with production migrations and changing it deserves its own change.

---

## P2-1 — Three tests are marked `@pytest.mark.asyncio` but are not async

`tests/test_sandbagging.py` lines 22, 26, 34. Pytest warns on each. They still execute, so this is
tidiness rather than a correctness gap — but the sandbagging detector is a money-relevant control
and warnings there are worth clearing so a real one is not lost in the noise.

---

## Not findings — checked and clean

Recorded so the negative results are not re-litigated.

- **Hand-rolled `Φ` vs scipy.** `pairing.normal_cdf` (via `math.erf`) agrees with
  `scipy.stats.norm.cdf` to better than `1e-12` across a dense grid from z = −8 to 8, plus tails
  to ±37. Every quoted clear probability depends on this function; it is correct.
- **Money invariants under property testing.** `sum(payouts) + rake == pot` holds across arbitrary
  pots, rake rates, winner counts and weight vectors, including pot-smaller-than-winner-count,
  0 bps, 10000 bps, weighted ties and all-zero weights.
- **No floats in the money path.** `rake_for`, `split_pot` and `split_weighted` contain no float
  literals, no true division and no `float()`/`round()` calls, verified by AST walk.
- **Audit-replay reproducibility.** The four production-observed bars reproduce exactly from
  stored inputs, and a room of identical members produces a room bar equal to the shared personal
  bar, across all 15 corpus cases.
