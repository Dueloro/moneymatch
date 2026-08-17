# What Changed — in plain English

Written for someone smart who is **not** a statistician and may not have written this code. If you
read one section, read *"The safety check that was switched off"*.

**Status: this is a partial pass, not a finished one.** It covers the groundwork and the first
critical fix. What is still outstanding is listed honestly at the end.

---

## 1. The one-paragraph summary

Money Match takes real money-shaped stakes and pays them out based on how you actually play. That
means two things have to be true: the numbers it quotes you have to be honest, and the safety
checks around them have to actually run. This pass built the equipment to prove the first, and
fixed a case where the second was **silently switched off in production**. The system is *not* yet
ready for real users — several known mispricing bugs are still open — but it is now measurable,
which it was not before.

---

## 2. How Money Match decides your bar

No formulas. The whole pipeline:

1. **We look at your recent games** on the account you linked.
2. **We work out your typical result and how much you bounce around** — an average, and a measure
   of consistency. Recent games count for more than old ones.
3. **We set you a personal target** ("your bar") pitched so you'd hit it about 35%, 20% or 10% of
   the time depending on the difficulty you picked. Harder tier, bigger number, bigger share.
4. **Everyone in the room pays their entry in.** The money in the pot is *other players' money* —
   the platform is not betting against you.
5. **Whoever hits their target splits the pot**, minus our 10% cut. Miss it and your entry funds
   the people who hit theirs. Play no qualifying game at all and **you get a full refund** — you
   cannot lose by not playing.

The important part: **you are playing against a number derived from your own history, not against
the other people in the room.** A better player gets a harder number.

---

## 3. The safety check that was switched off

This is the most important thing found, and the story is worth following because the *reason* it
survived matters more than the bug.

**What was wrong.** Money Match is not allowed to take stakes from residents of 14 US states. The
list lives in a database setting so it can be changed without a code deploy. The code that read
that list had a flaw: if it could not read the list — the setting was missing, empty, corrupted,
or the database hiccuped — it returned *"the list of banned states is empty"*.

An empty list of banned states means **nobody is banned**.

**What a player would have experienced.** A resident of an excluded state could have joined a
contest and staked money. Nothing would have errored. Nothing would have looked wrong. There is
no alert for this, and the only way anyone would find out is a regulator asking.

**A detail worth pausing on.** The line that did this had a comment directly above it saying
`# fail closed`, which means "when in doubt, refuse". The code underneath did the exact opposite.
That is a different and nastier category of defect than a normal bug: **anyone auditing this file
by reading it would have been reassured by a comment that was lying.** There were three such
paths, not one.

**What we changed.** The code now distinguishes *"these states are banned"* from *"we don't know
which states are banned"*, and treats the second as a refusal. An empty list now counts as
"unconfigured", not "nowhere is banned". Separately, a production deploy now **refuses to start**
if the list is missing or shorter than the 14 states it should have. A deploy that won't start is
loud and takes ten minutes to fix. A deploy that starts with no safety fence is silent and takes
months to discover.

**How we know it's fixed.** 24 new tests, covering every way the configuration can go wrong —
missing, empty, malformed, unreadable — plus each of the 14 states individually, plus the
start-up refusal.

### And now the part that actually mattered

When the fence was turned on, **about 90 existing tests failed.**

Not because the fix was wrong. Because *the tests had never had a fence in the first place.*

The test database was being built by a shortcut that skips the setup steps a real database goes
through. One of those steps is the one that loads the list of banned states. So in every test that
has ever run, the list was absent, the old code said "nobody is banned", and every test sailed
through happily.

**No test could ever have caught someone switching the safety check off, because no test ever
loaded it.** That is why the bug reached production.

So the fix went to the cause rather than the symptom: **the test database is now built the same
way the real one is**, by running the actual setup steps. It costs 3 extra seconds on a suite that
takes about 12 minutes.

Then we measured exactly how big the hole was — a list of everything the real database sets up
that the tests never saw. There were four discrepancies. One of them turned out to be a genuine
production problem nobody knew about (next section).

---

## 4. The kill switch that wasn't there

**What was wrong.** Every game has an on/off switch so it can be disabled in an emergency. When
CS2 moved from one data provider to another, the old game's switch was left behind and a new one
was never created. So the switch table has an "on" entry for a game that no longer exists, and
**no entry at all for the game that does.**

**What a player would experience.** Nothing, day to day — CS2 works fine, because the code assumes
"on" when there's no entry.

**Why it matters anyway.** If CS2 needs to be turned off in a hurry — Valve's servers break, the
match-reading service wedges, someone finds an exploit — the person doing it under pressure is
relying on a switch being *created correctly on the spot*, rather than flipping one that's already
there. Every other game has a real switch. This is the kind of thing you find out about at exactly
the wrong moment.

**What we changed.** A migration that creates the CS2 switch and removes the dead one, plus a test
that fails if any game is ever declared in code without a matching switch in the database.

---

## 5. The equipment we built before touching any maths

You cannot safely change how the numbers are calculated unless you can prove you didn't break
them. Three things now exist that didn't:

**A golden snapshot.** For 15 representative players, we record every number the system would
quote them and freeze it in a file. Any future change that moves any number must move it *in that
file*, deliberately, with the change explained. Four of those cases were read off the live
production app, so they anchor the maths to reality rather than to our own opinion.

**Money invariants, tested exhaustively.** The rule "everything paid out plus our cut equals
exactly what went in" is now tested against thousands of randomly generated scenarios — including
deliberately nasty ones like a pot smaller than the number of winners. Previously it was only
tested against cases someone thought of.

**A no-decimals guard.** Money is counted in whole cents, never fractions, because fractions
silently lose money. A test now reads the code itself and fails if a fraction ever appears in the
functions that move money.

### What the equipment found immediately

The golden snapshot caught something in its first run.

When we quote you a "10% difficulty" bar, we round the number to something displayable — K/D was
rounded to the nearest 0.05. **That rounding alone moves the true difficulty from 10% to 11.5%.**
You are being told 10% and getting 11.5%.

That matters beyond accuracy: an outside research report had blamed a similar-sized error on a
sophisticated statistical issue. It now looks like **at least part of it is just rounding** — a far
simpler and cheaper thing to fix. The two are being measured separately before either fix gets
credit, because otherwise you fix one and wrongly credit the other.

---

## 6. A dependency decision, explained

We added a well-known scientific-maths library (`scipy`) rather than writing those maths functions
ourselves. Writing your own version of five specialist statistical functions, in the code that
decides who gets paid, is a bigger risk than a larger install size.

Two safeguards came with it:

- The existing hand-written function that all the odds depend on was **checked against the
  library's version** across thousands of points. They agree to twelve decimal places. It was
  right, and it has been left alone — rewriting working code is its own risk.
- The library's exact version is **recorded alongside the frozen numbers**, so if a future upgrade
  nudges a number, we can tell it was the upgrade rather than someone's change.

---

## 7. What we still don't know

Honest list. Full detail in `OPEN_QUESTIONS.md` and `AUDIT_FINDINGS.md`.

- **The state list is self-declared.** The geo-fence checks the state you *typed* when you signed
  up. There is no location check of any kind. Someone can currently pick a different state. The
  fence is a posture, not a control, and closing that needs a vendor and a decision.
- **Whether the state list may ever be shortened is deferred**, pending legal advice. We made it a
  setting rather than deciding it in code.
- **The mispricing bugs are still open.** Notably: different CS2 game modes appear to share one
  skill model (a bar sold as 10% may be nearer 23% for someone who only plays Premier), and the
  headshot-percentage market is exploitable by deliberately getting very few kills. Both are known,
  both are next, neither is fixed.
- **No CS2 match has ever been collected in production.** The whole settlement path is unproven
  end to end against a real game.

---

## 8. What has to happen before real money

1. The two mispricing exploits above (mode split, headshot floor).
2. Version-stamping the maths, so a contest priced under old rules settles under old rules.
3. A calibration check — proving a "10%" bar really is cleared 10% of the time.
4. One real CS2 match settling end to end.
5. Legal: a state-by-state opinion, and a real location check rather than a typed one.
6. Payments, identity verification, and withdrawal controls — none of which exist yet.

---

## Glossary

| Term | Plain meaning |
| --- | --- |
| **Bar** | The personal target you have to beat |
| **Clear rate** | How often you'd expect to beat it |
| **Rake** | The platform's cut, currently 10% |
| **Escrow** | Your entry, held aside while the contest runs |
| **Pot** | Everyone's entries added together |
| **Room** | The 3–4 players in one contest |
| **Bucket** | A specific combination of game, stat, difficulty and entry size |
| **Fill rate** | How often enough people show up to actually start a contest |
| **Calibration** | Checking that a "10% chance" really happens 10% of the time |
| **Migration** | A recorded setup step that changes the database |
| **Share code** | The code CS2 gives you for a finished match |
| **Game Coordinator** | Valve's service that turns that code into a scoreboard |
| **Sidecar** | The small helper program that talks to it |
| **EWMA** | An average that weights recent games more heavily |
| **Prior** | A starting estimate used before we have enough of your own games |
| **Shrinkage** | Blending your own record toward that starting estimate |
