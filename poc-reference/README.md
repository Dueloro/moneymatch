# poc-reference — frozen PoC code (reference only)

A read-only mirror of the reusable parts of the MoneyMatch PoC (the
`clutchbook` repo, copied 2026-07-15). It exists so the implementation guide's
migration pointers resolve inside this repo.

**Rules:**

- Never `import` from this tree, deploy it, or edit it.
- Port code out of it per
  [`docs/implementation-guide/11-migration-map.md`](../docs/implementation-guide/11-migration-map.md)
  — with its tests, floats→cents, client-trust removed.
- [`POC-IMPLEMENTATION.md`](./POC-IMPLEMENTATION.md) is the code-verified
  ground truth of how this code behaved in the PoC (paths in it refer to the
  original repo layout: `api/…`, `src/…`, `tests/…`).

Contents: `api/` (FastAPI routes + `_lib` engines/adapters/services),
`tests/` (pytest suites — the settlement-invariant suite is the spec),
`frontend/src/` (types, hooks, utils, design-token CSS). The PoC's Electron
overlay and React components were deliberately not migrated (see migration map §3).
