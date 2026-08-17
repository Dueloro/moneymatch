# Next — continuation brief

Phase 0, Phase 1.1 and P0-1 are accepted. The migration-run-in-tests fix was the right call and
the CS2 kill-switch find (P1-1) was a genuine catch. Branch handling was correct.

Everything in `IMPLEMENTATION_PROMPT.md` still stands except the running order, which changes
below because of new analysis.

---

## New input: the ratio metrics are worse than the mode split

I ran the four metric families across all four games (script attached — commit it as
`docs/research/metric_families.py`). The finding that reorders the queue:

**Every metric shaped `X ÷ Y` is badly mispriced, in the direction that hurts players.** Bars are
too *hard*, so players lose more often than the card promised:

| Metric | Family | Easy tier: quoted → actual |
| --- | --- | --- |
| Dota 2 KDA | ratio | 35% → **20%**  (0.57×) |
| CS2 K/D | ratio | 35% → **25%**  (0.73×) |
| PUBG headshot % | proportion, tiny denominator | 35% → **21%**  (0.60×) |
| Dota 2 GPM | rate | 34% → 34%  (1.00×) |

Cause: ratios have a long right tail, which drags both the mean and the spread up, so `μ + k·σ`
lands where almost nobody goes. Same mechanism that once produced a "minus six moves" chess bar.

**Why this jumps the queue:** it affects two games, every entrant on those markets, and it is a
*consumer* problem (you are advertising 35% and delivering 20%) rather than only a pot-maths one.

**Why it is cheap:** the fix already exists in your codebase. `METRIC_POSITIVE_SUPPORT` routes
`chess_moves` to a lognormal for exactly this reason. Verify it behaves correctly for
higher-is-better metrics, then add the ratio metrics to it.

Treat my numbers as **hypotheses to verify against the golden harness**, not results — same rule
as `analysis.py`. If your harness disagrees, your harness wins; say so.

---

## Running order

1. **Phase 1.2–1.6** — the remaining small bugs. `clear_prob` answers `P(X > bar)` while grading
   is inclusive; on discrete metrics those differ by the mass at the bar.
2. **Phase 2.0** — model versioning. Prerequisite for everything below; nothing that moves a
   quoted number ships before it.
3. **Ratio distributions** — route `cs2_kd_ratio` and `dota2_kda_ratio` to the lognormal branch.
   Measure before and after per tier. Lognormal should get Dota easy from ~20% to ~31%; the
   remaining gap needs empirical quantiles, which is later work — log it, don't do it now.
4. **Phase 2.1 CS2 mode split** — **verify the premise first.** If Premier/Competitive/Wingman do
   not in fact share a model, say so and skip.
5. **Phase 2.2 headshot kill floor** — ≥12 kills to grade. Note the same denominator hole exists
   on K/D: same skill, fewer engagements per match, 4.2% → 25.9% on a bar priced at 10%. Design
   the floor so it generalises to both; implement headshot now, propose the K/D version.
6. **Phase 6 audit** — the systematic pass, especially matchmaking, settlement and payout
   idempotency.
7. **Phase 2.5 + 2.3** — increment change and Student-t, instrumented separately as agreed.
8. **Phase 5.1 calibration harness** — backtest mode first.

Stop and report after **3** and after **5**. Those two change quoted numbers for live markets and
I want to see the golden diff before you continue.

---

## Standing rules (unchanged, stated once)

- Branch `fixes/testing`. No force-push, no rebase of pushed work, `main` untouched.
- Test cadence as revised: targeted + golden + money invariants per change; full suite per commit;
  full suite + `alembic check` + reviewed golden diff per phase.
- Money invariants may not be weakened. Ever.
- Where the brief, the research or my numbers disagree with the code, **the code wins** — and say
  so in `OPEN_QUESTIONS.md` rather than working around it quietly.
- Flag legal/product judgements, don't make them.

---

## Loose ends from your own documents

- **P2-2** (`fileConfig` disabling existing loggers) — do the `env.py` follow-up as its own
  commit. You were right that it deserves one; it's small and the failure mode is missing logs.
- **P2-1** (three mis-marked async tests) — clear them. Warnings in a money-relevant control are
  where a real one goes to hide.
- **Q8** (self-attested residence, no location check) — acknowledged, not yours. Stays deferred
  with the rest of geo. Keep it prominent in `WHAT_CHANGED.md`; it is stated well there.
- **Web suite baseline** — capture it before Phase 1.2 touches card copy.

---

## Not asking for

No new games. No payments, KYC or geolocation vendors. No house-guaranteed pots. No further geo
work. Don't delete `test_opponents.py` yet.

Keep the honest status table in your reports — including the "not started" rows. That format is
working; don't start rounding it up.
