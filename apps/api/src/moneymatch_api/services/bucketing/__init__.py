"""The bucketing layer — one-bar-per-bucket ranking & matchmaking.

A self-contained addition on top of the existing adapters / markets / settlement
(it does not rewrite them). Ships behind the `bucketing_enabled` feature flag,
which defaults **off** — nothing here touches money until the flag is turned on.

Built in the phase order of `docs/implementation-guide/IMPLEMENTATION_BUCKETING.md`:

- `index`      — Phase 2: the best-of-40% skill index (pure).
- `reference`  — Phase 3: reference distributions, bucket cuts, assignment (pure).
- `placement`  — Phase 4: the two placement systems + the stake ladder (pure).
- `settlement` — Phase 5: grade-vs-bar + the money invariant (pure).
- `markets`    — the launch-scope market catalogue (game × mode × metric).
"""

from __future__ import annotations
