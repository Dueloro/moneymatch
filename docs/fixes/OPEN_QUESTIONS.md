# Open Questions

Running log for the production-hardening pass (`docs/IMPLEMENTATION_PROMPT.md`). Anything I had
to assume, anything out of scope, anything that smells wrong but I can't prove, and anywhere the
brief or the research disagrees with the code.

**Rule applied throughout: where the code disagrees with `MONEYMATCH_RESEARCH.md`, the code
wins** — the research was written without reading the source.

---

## Resolved

| # | Question | Resolution |
| --- | --- | --- |
| Q1 | `analysis.py` missing | **Supplied.** Committed at `docs/research/analysis.py` on its own. Treated as hypotheses to verify, not results to trust — it simulates synthetic models and was written without reading the source. |
| Q2 | "Full suite per change" vs a 12-minute suite | **Revised.** Per change: affected modules + golden harness + money invariants. Per commit: full suite. Per phase: full suite + `alembic check` + reviewed golden diff. |
| Q7 | Geo floor one-way editable | **DEFERRED** (see below) — but no longer hard-coded; it is now a setting with a fail-closed default. |
| Q9 | Suite ran with no geo-fence | **Fixed at the cause.** Test schema is now built by running migrations. Promoted to `AUDIT_FINDINGS.md` **P0-1**. |
| — | scipy vs hand-rolled numerics | **Decided: adopt scipy** as a runtime dependency, pinned `>=1.14,<2`, with a Φ reconciliation test, determinism tests, and the version recorded in the golden metadata. |

---

## Blocking / needs a human decision

### Q1. `analysis.py` does not exist in the repo — **RESOLVED, supplied**

Both `IMPLEMENTATION_PROMPT.md` ("reproducible via the `analysis.py` script delivered with it")
and `MONEYMATCH_RESEARCH.md` §2 ("All figures below are reproducible with the delivered
`analysis.py`") refer to a simulation script. A recursive search of the repo finds no file by
that name, and it is not in git.

**Consequence:** every quantitative claim in the research — the 2.35× mode-pooling mispricing,
the 51% headshot exploit clear rate, the 11.6% realised hard-tier rate, the 23.7% → 99.8% fill
rate figures — is **currently unverifiable locally**. I can re-derive them independently, and
where a number drives a decision I intend to, but that is materially more work than running a
delivered script.

**Ask:** can the script be supplied? If not, say so and I will rebuild the simulations from
scratch as a permanent repo tool (which Phase 3.3 requires anyway).

### Q2. "Run the FULL test suite after every change" versus a ~10-minute suite

Ground rule 1 requires the full suite after every single change; ground rule 2 requires one
logical change per commit. The API suite takes **~10 minutes** (measured — see baseline below).

**Interpretation I am applying:** full suite once per *logical change / commit*, not per edited
line, with the targeted tests run continuously in between. This is what the two rules together
seem to intend. Flagging it because a stricter reading would mean roughly one commit per hour
and would materially change how far through the brief I get.

---

## Findings that contradict the brief or the research

### Q3. The geo-fence fails open in **three** ways, not one

Brief 1.1 describes `excluded_states` reading "an empty feature flag". The actual fail-open
surface in `geo_service.py` is wider:

1. `SQLAlchemyError` on read → returns `set()` — and the inline comment on that line literally
   reads `# fail closed: unknown geo ⇒ treat as blocked-none`, which is self-contradictory. It
   fails **open**.
2. `flag is None` (no row) → returns `set()`.
3. Payload present but `excluded_states` key missing/empty/malformed → returns `set()`.

All three are fixed together in Phase 1.1. Noting it because the brief's description would have
led to fixing only the third.

### Q4. No existing test encoded the fail-open behaviour

I expected `test_geo_service.py::test_flag_change_takes_effect_without_deploy` to assert
fail-open (it ends with `assert_can_enter(session, "FL")  # no raise`). It does not — it sets a
non-empty list `["AZ"]` first, so it is asserting correct behaviour and survives the fix
unchanged. No pre-existing assertion had to be rewritten for 1.1.

### Q5. `test_fairness.py` hardcodes the stale difficulty constants

Brief 1.6 flags that `fairness.py`'s docstring claims `k = {0.5, 1.0, 1.75}` while
`POOL_DIFFICULTY_K` is `{0.385, 0.842, 1.282}`. The same stale values are also baked into
`tests/test_fairness.py`, which passes `k` explicitly and labels the values
`# Easy (k=0.5)`, `# Medium (k=1.0)`, `# Hard (k=1.75)` in comments.

Those tests are still *correct* — `personal_bar` takes `k` as a parameter, so they test the
arithmetic, not the constants. But the comments reinforce the wrong mental model. Fixing the
comments as part of 1.6.

---

## Dependencies added

- **`hypothesis`** — required by Phase 0.3 (property-based money invariants). Was not a
  dependency; added to the `dev` extra.
- **Student-t quantile (Phase 2.3) will need a decision.** The codebase has no `scipy` and
  implements `Φ` by hand via `math.erf`. Options: (a) add `scipy`, a heavy dependency for one
  function; (b) implement the t-quantile directly. Leaning (b) to keep the dependency surface
  flat, with the implementation tested against known quantile tables. Flagging before doing it.

---

## Baseline (Phase 0.1)

Recorded before any source change, against commit `ede7ce6`.

- **Migrations:** 24 files, head `0024_retire_cs2_faceit`. `alembic check` → *"No new upgrade
  operations detected."* ✅
- **API suite: 1052 passed, 0 failed, 0 skipped, 4 warnings, in 662.71s (11m02s).** Green.
  - Note: `IMPLEMENTATION_STATUS.md` §16 and the brief both say ~1,028 collected. The actual
    figure is **1052**. Corrected in the status doc.
  - The 4 warnings are pre-existing and harmless: one short HMAC key in `test_auth.py`, and
    three tests in `test_sandbagging.py` marked `@pytest.mark.asyncio` that are not async
    functions. The latter is worth tidying but changes no behaviour.
  - The three Phase 0 test files I added were written *after* collection began, so they were
    not counted — this is a clean pre-change baseline.
- **Web suite:** not yet run (deferred to the first web-touching change; no Phase 0–2 item
  changes web code).

**Post-Phase-0 count: 1052 + 37 = 1089 passing.**

---

## Findings from the Phase 0 harness itself

### Q6. Bar rounding moves the true clear rate by up to 15% relative — confirmed from code

The golden snapshot records `p_target` (the difficulty's design clear rate) alongside `p_quoted`
(the probability of clearing the bar **as actually rounded and quoted**). They diverge:

| CS2 K/D (μ=1.00, σ=0.25, increment 0.05) | p_target | p_quoted | Error |
| --- | --- | --- | --- |
| Easy | 35.01% | 34.46% | −0.55pp |
| Medium | 19.99% | 21.19% | +1.20pp |
| **Hard** | **9.99%** | **11.51%** | **+1.51pp (15% relative)** |

This independently confirms `MONEYMATCH_RESEARCH.md` §2.5 (bar-increment coarseness) **from the
codebase rather than from its simulation** — the research's `analysis.py` was not needed. It also
means the K/D increment change in Phase 2.5 (0.05 → 0.01) is justified on measured grounds.

Worth noting for Phase 2.3: part of what the research attributes to the plug-in normal is
actually *rounding*, and the two need to be separated before either fix is credited with a
number. The golden file makes that separable.

---

## Significant findings

### Q9. The entire test suite has been running with **no geo-fence at all**

Found while fixing 1.1: turning the fence on broke **~90 tests** across pools, tournaments,
matchmaking and endpoints. The cause is not the fix — it is that the fence was never exercised.

Three things compound:

1. `tests/conftest.py` builds the schema with `Base.metadata.create_all`, **not** by running
   migrations. So migration 0001's seed data — including the 14-state `geo_config` row — never
   existed in the test database.
2. The `_clean` fixture then deletes all feature flags and reseeds from
   `feature_flags.DEFAULT_FLAGS`, which **contains no `geo_config` entry at all**.
3. Under the old fail-open code, an absent flag returned an empty set, and an empty set excludes
   nobody — so every contest-entry test sailed straight through a fence that was not there.

**No test would have caught a regression that disabled the geo-fence entirely.** That is why the
fail-open bug survived to production. Fixed by seeding `geo_config` in `_clean` exactly as
migration 0001 does; the default test user is in MA, which is not excluded, so no assertion had
to change. Suite went 1052 → 1123 passing.

**Wider implication worth a decision:** because tests use `create_all` rather than migrations,
**no migration seed data is covered by any test**, and `create_all` can drift from the migration
chain without failing anything. `alembic check` catches model-vs-migration drift but not
seed-data drift. Candidate follow-up (out of scope here): build the test schema by running
migrations, or add a test that asserts `create_all` + seeds == migrated schema.

---

## Needs a product/legal decision

### Q7. The prod geo-fence floor makes the list one-way editable — **DEFERRED**

> **Status: DEFERRED, not decided** (per `REPLY_TO_AGENT.md` §2). To be revisited once the
> state-by-state legal opinion exists. No further geo work in this pass.
>
> **Resolution applied in the meantime:** the strictness is no longer hard-coded. It sits behind
> `Settings.geo_enforce_seeded_floor`, **defaulting to `True`** (strict). The deferred decision can
> therefore be made later by configuration rather than by a code change.
>
> Note the split, which is deliberate: relaxing that setting does **not** permit an absent, empty,
> malformed or unreadable fence. That check is unconditional and is not the part being deferred —
> it was the live hole in production. Only the *seeded-floor* requirement is configurable.

Brief 1.1 asks for a startup assertion that refuses to boot in `ENV=prod` if the excluded-state
list "is empty or does not contain all 14 seeded states". Implemented as specified
(`geo_service.assert_configured_for_production`, floor in
`constants.GEO_REQUIRED_EXCLUDED_STATES`).

**The tension:** the whole reason the list lives in a feature flag rather than a code constant is
that it "changes without a deploy". The floor makes that true in one direction only — an admin
can *widen* the fence live, but narrowing it below the seeded 14 now requires a code change and a
deploy.

That is almost certainly the right default for a fence that only ever loosens under legal advice.
But it is a product decision, not an engineering one, and it should be a deliberate answer to:
*if a state's legal position changes in our favour, are we content that re-opening it takes a
deploy?* Flagging rather than deciding, per the brief's rule on legal judgements.

### Q8. `residence_state` is self-attested and never verified

Out of scope for this pass (the brief forbids wiring geolocation vendors), but worth stating
plainly because the geo-fence work above could otherwise read as stronger than it is: the fence
gates on `users.residence_state`, which the user types during onboarding. There is no IP check,
no device geolocation and no address verification anywhere in the codebase. **A blocked resident
can currently pass the fence by selecting a different state.**

The fence is therefore a compliance *posture*, not a control. Before real money, that gap needs
either a geolocation vendor or an explicit written acceptance of the risk.

---

## Deferred / out of scope for this pass

- **Module coverage measurement (Phase 0.1).** Deferred: an instrumented full run costs another
  ~11 minutes and the test database is shared, so it cannot run alongside the verification runs
  this pass needs. Will capture in one pass alongside a later full-suite run.
- **Web suite baseline.** Not run — no Phase 0–2 item touches web code. Will run before the
  first web-facing change (Phase 1.2 card copy).
