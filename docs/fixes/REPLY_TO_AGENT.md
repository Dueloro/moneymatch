# Reply — branch change, geo deferred, dependency decision, re-prioritised order

Good work. The geo-fence finding and the rounding-vs-distribution separation are both better
than what the brief gave you. Four instructions below, then a change to the running order.

---

## 1. Branch — move everything to `fixes/testing`

**Do not continue on `hardening/production-pass`.** A branch called `fixes/testing` already
exists and is the one this work belongs on. Move the three existing commits there and work there
from now on.

Before moving anything, check what state `fixes/testing` is actually in:

```
git fetch --all
git log --oneline main..fixes/testing
git log --oneline main..hardening/production-pass
```

Then pick the matching case:

- **If `fixes/testing` has no commits of its own** (it's sitting at `main`): fast-forward it.
  `git checkout fixes/testing && git merge --ff-only hardening/production-pass`
- **If `fixes/testing` has its own commits:** cherry-pick the three across in order, resolve any
  conflicts deliberately, and re-run the full suite afterwards to confirm nothing regressed in
  the transfer.

Then delete `hardening/production-pass` locally and remotely so nobody works on it by mistake.

Rules: **do not force-push. Do not rebase anything already pushed. Do not touch `main`.** If any
step looks like it would rewrite shared history, stop and describe the situation instead of
proceeding.

Confirm in your next status update that the branch is `fixes/testing`, the three commits are
present, and the full suite is green on it.

---

## 2. Geo-fence — stop here, this is deferred

No further work on geo. Specifically:

**Keep** (already done, do not revert):

- The fail-closed behaviour itself. An empty, missing or malformed excluded-state config must
  block, not allow. That was a live hole in production and reverting it would reopen it. This is
  not the part being deferred.
- The `conftest.py` fixture fix that mirrors migration 0001. That's a test-infrastructure fix and
  it's the thing that exposed the whole class of problem — see §5.
- The corrected comments. A `# fail closed` comment above `return set()` is its own defect.

**Defer** (do no more work on these):

- Q7, the one-way editability question. Mark it **DEFERRED**, not decided, in
  `OPEN_QUESTIONS.md`. Note that it's a product/legal decision that will be revisited once the
  state-by-state legal opinion exists.
- Any further geo hardening: no geolocation vendor work, no state-list revision, no additional
  admin tooling around the fence.

**One adjustment before you leave it:** the production boot assertion currently makes the
excluded-state list one-way editable as a permanent architectural fact. Since that's the exact
decision being deferred, don't leave it hard-coded. Put the strictness behind a single
configuration value with a **fail-closed default** (i.e. it refuses to boot with a holed fence
unless explicitly configured otherwise), so the decision can be made later by configuration
rather than by a code change. Keep the current strict behaviour as the default. Then stop.

---

## 3. Dependency — add scipy, do not hand-roll

**Reversing the earlier guidance in the brief.** Add `scipy` as a real runtime dependency.

The earlier answer was scoped to one function (the Student-t quantile) and was wrong for that
reason. The roadmap needs several more pieces of specialist numerics, all of which scipy already
provides, tested, at scale:

| Needed for | scipy provides |
| --- | --- |
| Phase 2.3 Student-t predictive bar | `scipy.stats.t.ppf` |
| Phase 2.2 beta-binomial headshot model | `scipy.stats.betabinom` |
| Phase 2.4 negative binomial kills | `scipy.stats.nbinom` |
| Phase 5.1 Wilson intervals on the reliability diagram | `scipy.stats.binomtest(...).proportion_ci(method="wilson")` |
| Phase 3.3 / 4.2 simulation work | `scipy.stats` generally |

Hand-rolling five special functions in the code path that decides where money goes is a worse
risk than tens of megabytes of deployment size. If deploy size later proves to be a real,
measured problem, that's a problem to solve with evidence at that point — not a constraint to
optimise against now on a guess.

Implementation notes:

- **Do not churn the existing hand-rolled Φ** (`math.erf`). It works, it's covered, and
  rewriting working code is its own risk. Build everything *new* on scipy.
- **Do add one reconciliation test:** assert the existing hand-rolled Φ agrees with
  `scipy.stats.norm.cdf` across a grid including the tails, to a stated tolerance. If they
  disagree anywhere that matters, that is a finding — report it, don't silently patch it.
- **Pin the scipy version** and record it in the golden-snapshot metadata. A library upgrade that
  moves a quantile in the 6th decimal place could move a rounded bar; the golden file must be
  able to attribute that.
- **Determinism matters more than elsewhere here.** Anything feeding the money path must produce
  identical output for identical input across runs and platforms. Add a test asserting that.

---

## 4. `analysis.py`

It exists; it was never committed. It is attached alongside this reply. Put it in
`research/analysis.py` and commit it on its own so the provenance is clear.

Two caveats:

- It is a **simulation against synthetic generative models**, not a measurement of our code. It
  was written before anyone read the source. Where it and the codebase disagree, the codebase
  wins — you've already demonstrated exactly why.
- Treat it as a source of *hypotheses to verify*, not results to trust. Your golden-harness
  measurement (K/D hard: `p_target` 9.99% vs actual clear 11.51%) is stronger evidence than
  anything in that file, because it came from real code.

---

## 5. The test/migration gap — promote this to its own P0

You buried the most important finding under "what surprised me." Restating it so it doesn't get
lost:

> `conftest.py` builds the schema with `create_all`, so no migration ever runs in tests, so **no
> seed data is covered by any test**, and `create_all` can drift from the migration chain
> silently. `alembic check` catches model drift, not seed drift.

That is the root cause of the geo-fence bug reaching production, and — unlike the geo-fence
itself — **it is not deferred.** The fence was one symptom; the gap is the disease, and it is
almost certainly hiding others.

1. Add it to `AUDIT_FINDINGS.md` as **P0 in its own right**, separate from the geo fix.
2. **Enumerate everything migration-seeded that no test covers.** Start by diffing `DEFAULT_FLAGS`
   against what the migration chain actually inserts. Report the full list before fixing
   anything — I want to see the size of the hole.
3. **Propose a fix and say which you'd pick.** Two candidates: (a) run migrations in the test
   fixture instead of `create_all` — slower, but eliminates the drift class entirely; (b) keep
   `create_all` and add a test asserting seeded state matches the migration chain. I lean (a) if
   the runtime cost is tolerable, because (b) is one more thing that can itself drift. Measure
   the runtime cost of (a) before deciding.

For the write-up later: the reason this bug survived is a *good* story for `WHAT_CHANGED.md` —
"the safety check was switched off, and the tests couldn't have noticed because they never loaded
the list in the first place" is understandable by anyone, and it shows the fix went to the cause
rather than the symptom.

---

## 6. Re-prioritised running order

You're right that the brief is weeks of work. Two changes.

### Relax the "full suite per logical change" rule

The intent was "never batch fixes and test at the end," not "pay 13 minutes per edit." Revised:

- **Per logical change:** affected test modules + the golden-snapshot harness + the money-invariant
  tests. Fast.
- **Per commit:** full suite, must be green.
- **Per phase:** full suite + `alembic check` + a reviewed golden-file diff.

The golden harness and money invariants run on every change regardless. Those are the two that
catch silent damage.

### New order

Finish Phase 1, pull the two *exploits* out of Phase 2 and do them early, then audit, then return
for the accuracy work.

```
1.  Phase 1.2 - 1.6           remaining small bugs (geo 1.1 done and deferred)
2.  Phase 5.5 test/migration  the P0 from section 5 above
3.  Phase 2.0 model versioning prerequisite for anything that moves a quoted number
4.  Phase 2.1 CS2 mode split   VERIFY FIRST. If real: 2.35x mispricing, player-selected
5.  Phase 2.2 headshot floor   ~10x mispricing, needs no tooling to exploit
6.  Phase 6   independent audit unknown unknowns in matchmaking, settlement, money
7.  Phase 2.5 + 2.3 as a pair  see section 7 below
8.  Phase 5.1 calibration      backtest mode first; needs no live traffic
9.  everything else, in brief order
```

Rationale: items 1–6 are things that let someone take money they shouldn't, or that break for a
real user. Items 7+ make honest odds *more precisely* honest — which matters, but matters most
once contests are actually settling, and none have.

**Phase 3.4 (fill window / play window split) stays where it is.** It's the largest state-machine
change in the brief and it is not an emergency.

---

## 7. Rounding vs distribution — instrument these separately

This is the most valuable thing in your report and I want it to land in the plan properly.

You measured K/D hard at `p_target` 9.99% vs actual clear 11.51% — 15% relative — **from rounding
alone**, and correctly noted that §2.6 of the research attributes a similar-sized gap to the
plug-in normal. Two separate causes producing overlapping symptoms. Neither can be credited until
they're separated.

So do 2.5 (increment) and 2.3 (Student-t) as an explicitly instrumented pair, in this order:

1. Measure the current gap per metric × difficulty from the golden harness. That's the baseline.
2. Change the K/D increment `0.05 → 0.01` **alone**. Re-measure. Attribute that delta to rounding.
3. Apply the Student-t predictive **alone**, on top. Re-measure. Attribute that delta to
   distribution.
4. Record all three measurements in the commit messages and carry them into `WHAT_CHANGED.md`.

**If step 3's delta comes out much smaller than the research predicted, that is a real finding and
should be written up as one** — it would mean the research over-credited the statistics and
under-credited the quantisation. Say so plainly; don't quietly absorb it.

While you're there: apply the same `φ(k)/σ · increment` audit to **every** metric, not just K/D,
and add the assertion test the brief asks for so a coarse increment can't ship again.

---

## 8. Corrections to carry forward

- Test baseline is **1052**, not ~1028. Correct it in the brief, in `IMPLEMENTATION_STATUS.md`
  §16, and anywhere else the wrong number appears.
- Phase 1.1 was **three** fail-open paths, not one — including one with `# fail closed` directly
  above `return set()`. Worth calling out specifically in `WHAT_CHANGED.md`; a comment that
  contradicts its own code is a distinct category of defect from a plain bug, and it's precisely
  why nobody caught it by reading.
- Phase 1.2 is **half done, not wrong.** Grading is already consistently inclusive
  (`telemetry_fetch.py:177`, `live_activity_service.py:116`). The live defect is that `clear_prob`
  answers `P(X > bar)` from a continuous normal while grading is `P(X >= bar)` — on discrete
  metrics (kills, `chess_moves`) those differ by the point mass sitting exactly at the bar. Fix
  that half; drop the operator-consistency half; note the correction in your status.

Keep going, and keep flagging where the brief is wrong. You've been right twice.
