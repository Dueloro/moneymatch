# Adding a new `market.kind`

A **market kind** is the _shape_ of a contest — how it is graded and what a
baseline means — as opposed to a **game** (which host it runs on) or a **metric**
(which stat it scores). Adding a kind is rarer and more invasive than adding a
game: a game plugs in behind the adapter and touches nothing shared, but a kind
teaches the shared engines a new way to decide who won, so it necessarily touches
several files at once.

Today there are three kinds, defined in `services/markets.py`:

| Kind constant | Value | Grades on |
| --- | --- | --- |
| `KIND_WIN_H2H` | `win_h2h` | Who won a brokered head-to-head game |
| `KIND_WIN_NEXT` | `win_next` | Whether your next game is a win |
| `KIND_STAT_RACE` | `stat_race` | A rate metric (K/D, accuracy, …) vs. a bar |

## Before you start

A new kind is justified only when an existing one cannot express the contest.
"Score the mean of the first N matches" did **not** need a new kind — it reused
`stat_race`. If you can model your contest as an existing kind with different
config, do that instead. A kind is the heaviest thing you can add.

## The touch points (all in one PR)

A new kind is not done until every one of these is handled. Grep the existing
kinds (`rg 'KIND_STAT_RACE'`) to see every branch you must extend.

1. **`services/markets.py`** — declare the constant and add `MarketDef` entries
   (and any predicate like `is_win_h2h`). This is the catalog everything else
   reads.
2. **`constants.py`** — if the kind introduces metrics: add them to
   `POOL_METRICS` / `TOURNAMENT_METRICS`, `METRIC_LABELS`, and
   `METRIC_BAR_INCREMENT`. `test_docs_do_not_drift.py` will fail if a live market
   has no increment, or an increment has no live market — so keep these in lockstep.
3. **`adapters/base.py` (the contract, not the code)** — decide what the adapter
   must surface for this kind. Win kinds read `NormGame.won`/`drawn`; stat kinds
   read `NormGame.metrics` / `TelemetrySample`. If your kind needs a field no
   `NormGame` carries, that is a contract change every adapter must satisfy —
   think hard before adding one.
4. **`services/grading.py`** — the core work. Add the branch that turns a host
   result into an outcome for this kind. This is where "who won" is decided;
   every existing kind has a branch here.
5. **`services/matchmaking.py`** — extend baseline construction (`_build_baseline`)
   and eligibility (`_assert_eligible`) for the kind: what makes two entrants
   comparable, and what makes a user eligible to enter.
6. **The engines** — `pool_engine.py` / `tournament_engine.py` only if the kind is
   offered as a pool/field (H2H-only kinds skip these). Bar placement and field
   formation read the metric model via `metric_models_service.get_metric_model`.
7. **Tests** — a new kind must not break the money-invariant suites
   (`test_money_invariants_property.py`, `test_no_floats_in_money_path.py`). Add a
   grading test for the kind covering win, loss, draw/push, and unverifiable →
   refund. Add golden bars if it quotes a bar (`test_bar_golden.py`).
8. **`make gen-api`** — regenerate the client so the web app sees the new kind.

## The invariant that governs every kind

Whatever the kind, grading must be **server-derived and fail-closed**: the API
never accepts a score, rank, or outcome; an unverifiable entrant is refunded, not
guessed at; and all money is integer cents. A new kind that cannot be graded from
server-fetched data is not a kind we can offer for money. See
[`agent-handoff.md`](agent-handoff.md).
