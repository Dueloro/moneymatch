# Open Questions

Running log for the production-hardening pass (`docs/IMPLEMENTATION_PROMPT.md`). Anything I had
to assume, anything out of scope, anything that smells wrong but I can't prove, and anywhere the
brief or the research disagrees with the code.

**Rule applied throughout: where the code disagrees with `MONEYMATCH_RESEARCH.md`, the code
wins** — the research was written without reading the source.

---

## Blocking / needs a human decision

### Q1. `analysis.py` does not exist in the repo

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

## Deferred / out of scope for this pass

_(populated as encountered)_
