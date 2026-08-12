# PUBG Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PUBG fully playable and safe to settle — unblock stat duels, stop settlement mis-reading host outages/rate-limits, throttle PUBG API calls, and gate settlement to official match modes.

**Architecture:** Game-local changes only. A new `HostRateLimited` error + a process-local token bucket in the PUBG host client; the PUBG poll path lets outages propagate so the existing grading watchdog extends the window; the adapter raises its match fan-out, filters to official modes, and early-exits by timestamp; a generic `defer_bootstrap` seam moves PUBG's link-time metric bootstrap to the settlement worker (via a new `models_bootstrapped_at` column). Matchmaking, escrow, the money settlement path, and the other adapters are untouched.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy + Alembic, httpx + tenacity, respx + pytest-asyncio, Postgres.

**Reference spec:** `docs/superpowers/specs/2026-08-12-pubg-completion-design.md`

**Test DB note:** API pytest needs a throwaway Postgres on `:5433` (`moneymatch_test`). Run tests from `apps/api` with the venv active. Adapter/host/limiter unit tests are respx-only (no DB); bootstrap tests need the DB.

---

## File Structure

**New files:**
- `apps/api/migrations/versions/0019_link_bootstrap_at.py` — adds `linked_accounts.models_bootstrapped_at`.
- `apps/api/migrations/versions/0020_seed_pubg_flag.py` — seeds `game:pubg.steam` feature flag.
- `apps/api/tests/test_pubg_rate_limit.py` — token-bucket unit tests.
- `apps/api/tests/test_pubg_settlement.py` — outage/rate-limit propagation → `host_error` grading test.

**Modified files:**
- `apps/api/src/moneymatch_api/services/hosts/errors.py` — add `HostRateLimited`.
- `apps/api/src/moneymatch_api/services/hosts/_client.py` — map 429 → `HostRateLimited`, don't retry it.
- `apps/api/src/moneymatch_api/services/hosts/pubg.py` — rate limiter; propagate outages in `get_player_by_id`/`get_match`.
- `apps/api/src/moneymatch_api/config.py` — `pubg_rate_limit_per_min`.
- `apps/api/src/moneymatch_api/constants.py` — `PUBG_MATCH_FANOUT`, official-mode allowlists.
- `apps/api/src/moneymatch_api/adapters/base.py` — `defer_bootstrap` flag.
- `apps/api/src/moneymatch_api/adapters/pubg.py` — mode filter, fan-out, early-exit, `defer_bootstrap`, kd comment, link message.
- `apps/api/src/moneymatch_api/models/linked_account.py` — `models_bootstrapped_at` column.
- `apps/api/src/moneymatch_api/services/linking_service.py` — defer bootstrap for deferred adapters in `bind`/`refresh`.
- `apps/api/src/moneymatch_api/workers/settlement_worker.py` — `_bootstrap_pending_models` sweep in `run_forever`.
- `apps/api/tests/conftest.py` — neutralize the PUBG limiter for the suite.
- `apps/api/tests/test_pubg_adapter.py` — fixtures + mode-filter/fan-out tests + docstring fix.
- `apps/api/tests/test_host_clients.py` — 429 mapping tests.

---

## Task 0: Branch + commit the spec & plan

**Files:** none (git only)

- [ ] **Step 1: Create a dedicated branch off `main`**

```bash
cd /Users/shreyansh/Desktop/moneymatch
git checkout main
git pull --ff-only || true
git checkout -b feat/pubg-completion
```

- [ ] **Step 2: Commit the design + plan docs**

```bash
git add docs/superpowers/specs/2026-08-12-pubg-completion-design.md \
        docs/superpowers/plans/2026-08-12-pubg-completion.md
git commit -m "docs(pubg): completion design + implementation plan"
```

---

## Task 1: `HostRateLimited` error + 429 mapping

**Files:**
- Modify: `apps/api/src/moneymatch_api/services/hosts/errors.py`
- Modify: `apps/api/src/moneymatch_api/services/hosts/_client.py`
- Test: `apps/api/tests/test_host_clients.py`

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/test_host_clients.py`:

```python
import httpx
import pytest
import respx

from moneymatch_api.services.hosts._client import request_json
from moneymatch_api.services.hosts.errors import HostRateLimited, HostUnavailable


def test_rate_limited_is_a_host_unavailable_subclass():
    # So every `except HostUnavailable` (grading watchdog) treats a 429 as a
    # transient outage that extends the window, never a wrong settle.
    assert issubclass(HostRateLimited, HostUnavailable)


@respx.mock
async def test_429_maps_to_host_rate_limited_and_is_not_retried():
    route = respx.get("https://api.example.com/x").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(HostRateLimited):
        await request_json("example", "GET", "https://api.example.com/x")
    assert route.call_count == 1  # not retried — retrying only burns more budget


@respx.mock
async def test_5xx_still_retries_as_host_unavailable():
    route = respx.get("https://api.example.com/y").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(HostUnavailable):
        await request_json("example", "GET", "https://api.example.com/y")
    assert route.call_count == 3  # 2 retries + original
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && python -m pytest tests/test_host_clients.py -k "rate_limited or 429 or 5xx_still" -v`
Expected: FAIL — `ImportError: cannot import name 'HostRateLimited'`.

- [ ] **Step 3: Add the error class**

In `apps/api/src/moneymatch_api/services/hosts/errors.py`, after `HostUnavailable`:

```python
class HostRateLimited(HostUnavailable):
    """The host rejected the call with 429 (rate limit).

    A transient, budget-shaped failure. It subclasses `HostUnavailable` so the
    grading watchdog extends the settlement window instead of consuming it, but
    it is deliberately not retried in-call (an immediate retry only spends more
    of the same budget)."""
```

- [ ] **Step 4: Map 429 in the client**

In `apps/api/src/moneymatch_api/services/hosts/_client.py`:

Update the import:

```python
from .errors import HostError, HostNotFound, HostRateLimited, HostUnavailable
```

Change the retry predicate so `HostRateLimited` is not retried. Update the imports at the top:

```python
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)
```

and the `AsyncRetrying(...)` call:

```python
    async for retry in AsyncRetrying(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_random_exponential(multiplier=0.2, max=2.0),
        retry=(
            retry_if_exception_type(HostUnavailable)
            & retry_if_not_exception_type(HostRateLimited)
        ),
        reraise=True,
    ):
```

Add the 429 branch immediately after the `>= 500` check and before the generic `>= 400` branch:

```python
            if response.status_code >= 500:
                raise HostUnavailable(host, f"{method} {url} → {response.status_code}")
            if response.status_code == 429:
                raise HostRateLimited(host, f"{method} {url} → 429")
            # Any other non-2xx (400/401/403/422…) is a typed, non-retryable
```

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/api && python -m pytest tests/test_host_clients.py -v`
Expected: PASS (all, including pre-existing host-client tests).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/moneymatch_api/services/hosts/errors.py \
        apps/api/src/moneymatch_api/services/hosts/_client.py \
        apps/api/tests/test_host_clients.py
git commit -m "feat(hosts): typed HostRateLimited for 429 (transient, not retried)"
```

---

## Task 2: PUBG poll path propagates outages (Issue 2)

**Files:**
- Modify: `apps/api/src/moneymatch_api/services/hosts/pubg.py:83-101` (`get_player_by_id`), `:128-150` (`get_match`)
- Test: `apps/api/tests/test_pubg_settlement.py` (new)

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_pubg_settlement.py`:

```python
"""PUBG settlement resilience: a host outage / rate-limit during the poll must
surface as PENDING(host_error) so the worker EXTENDS the window, never as a
silent "no qualifying game" that consumes it. No DB — grade() only reads attrs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import respx

from moneymatch_api.config import get_settings
from moneymatch_api.services import grading
from moneymatch_api.services.hosts import pubg

SHARD = "https://api.pubg.com/shards/steam"


@pytest.fixture
def pubg_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "pubg_api_key", "test-key")
    pubg.clear_match_cache()
    yield
    pubg.clear_match_cache()


def _match_obj():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        game="pubg.steam",
        market="win_next",
        matched_at=now - timedelta(hours=1),
        window_ends_at=now + timedelta(hours=23),
    )


def _seats():
    return [
        SimpleNamespace(user_id=uuid.uuid4(), host_account_id="account.a"),
        SimpleNamespace(user_id=uuid.uuid4(), host_account_id="account.b"),
    ]


@respx.mock
async def test_outage_during_poll_yields_host_error(pubg_key):
    respx.get(f"{SHARD}/players/account.a").mock(return_value=httpx.Response(503))
    outcome = await grading.grade(_match_obj(), _seats(), datetime.now(UTC))
    assert outcome.status == grading.PENDING
    assert outcome.host_error is True


@respx.mock
async def test_rate_limit_during_poll_yields_host_error(pubg_key):
    respx.get(f"{SHARD}/players/account.a").mock(return_value=httpx.Response(429))
    outcome = await grading.grade(_match_obj(), _seats(), datetime.now(UTC))
    assert outcome.status == grading.PENDING
    assert outcome.host_error is True
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && python -m pytest tests/test_pubg_settlement.py -v`
Expected: FAIL — `host_error is False` (the 503/429 is currently swallowed to `None` → poll returns `[]` → PENDING without `host_error`).

- [ ] **Step 3: Propagate outages in `get_player_by_id`**

In `apps/api/src/moneymatch_api/services/hosts/pubg.py`, update the import line:

```python
from .errors import HostError, HostNotConfigured, HostNotFound, HostUnavailable
```

Replace the body of `get_player_by_id` try/except (currently `except HostNotFound: return None` / `except HostError: return None`):

```python
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{PUBG_BASE}/{shard}/players/{account_id}",
            headers=_headers(),
        )
    except HostUnavailable:
        # Outage / rate-limit (429): propagate so settlement grading extends the
        # window instead of reading it as "no such player / no qualifying game".
        raise
    except HostError:
        return None  # 404 / other 4xx → "no such player / unreadable"
    try:
        return (response.json() or {}).get("data")
    except ValueError:
        return None
```

- [ ] **Step 4: Propagate outages in `get_match`**

Replace `get_match`'s try/except (currently `except (HostError, ValueError): return None`):

```python
    try:
        response = await request_json(
            HOST,
            "GET",
            f"{PUBG_BASE}/{shard}/matches/{match_id}",
            headers=_headers(),
            timeout_s=10.0,
        )
        data = response.json()
    except HostUnavailable:
        # An unreadable match might be the qualifying one — propagate so grading
        # extends the window rather than silently grading a later match.
        raise
    except (HostError, ValueError):
        return None  # 404 (expired match) / other 4xx / bad JSON → skip this match
    _match_cache[match_id] = (time.monotonic(), data)
    return data
```

- [ ] **Step 5: Add a clarifying comment to `get_lifetime`**

In `get_lifetime`, above its `except HostError: return None`, add:

```python
    try:
        response = await request_json(...)  # existing call, unchanged
    except HostError:
        # Deliberately fail-soft on ALL host errors (incl. outages): lifetime is a
        # soft profile / bracketing signal, never settlement. A momentary gap must
        # not fail linking; the profile just computes from what modes returned.
        return None
```

(Only add the comment; the `except HostError: return None` stays as-is.)

- [ ] **Step 6: Run to verify pass**

Run: `cd apps/api && python -m pytest tests/test_pubg_settlement.py tests/test_pubg_adapter.py -v`
Expected: `test_pubg_settlement.py` PASS. `test_pubg_adapter.py` may now FAIL on the mode filter (fixed in Task 4) — note which failures are mode-related and defer them; the link/outage tests here must pass.

If any *outage* assertions in `test_pubg_adapter.py` regress, fix now; mode-filter failures are expected and handled in Task 4.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/moneymatch_api/services/hosts/pubg.py \
        apps/api/tests/test_pubg_settlement.py
git commit -m "fix(pubg): propagate host outages/429 on the settlement poll path"
```

---

## Task 3: PUBG rate limiter + config

**Files:**
- Modify: `apps/api/src/moneymatch_api/config.py:47-51`
- Modify: `apps/api/src/moneymatch_api/services/hosts/pubg.py`
- Modify: `apps/api/tests/conftest.py`
- Test: `apps/api/tests/test_pubg_rate_limit.py` (new)

- [ ] **Step 1: Neutralize the limiter for the suite**

In `apps/api/tests/conftest.py`, next to the existing `RATE_LIMIT_WRITES_PER_MINUTE` env line, add:

```python
# The PUBG host client throttles to ~9 req/min in prod; keep it out of the way of
# respx-mocked tests (the token bucket itself is proven in test_pubg_rate_limit.py).
os.environ["PUBG_RATE_LIMIT_PER_MIN"] = "100000"
```

- [ ] **Step 2: Write the failing test**

Create `apps/api/tests/test_pubg_rate_limit.py`:

```python
"""Token-bucket limiter for the PUBG host client (process-local; ~9 req/min)."""

from __future__ import annotations

import asyncio
import time

import pytest

from moneymatch_api.services.hosts.pubg import _TokenBucket


async def test_bucket_allows_burst_up_to_capacity_without_waiting():
    bucket = _TokenBucket(rate_per_min=6)  # capacity 6, refill 0.1/s
    started = time.monotonic()
    for _ in range(6):
        await bucket.acquire()
    assert time.monotonic() - started < 0.1  # full bucket → no waiting


async def test_bucket_throttles_once_capacity_is_spent():
    bucket = _TokenBucket(rate_per_min=60)  # capacity 60, refill 1/s
    for _ in range(60):
        await bucket.acquire()
    started = time.monotonic()
    await bucket.acquire()  # 61st must wait ~1s for a refill
    waited = time.monotonic() - started
    assert 0.5 <= waited <= 2.0


async def test_bucket_is_concurrency_safe():
    bucket = _TokenBucket(rate_per_min=6)
    await asyncio.gather(*(bucket.acquire() for _ in range(6)))  # no deadlock
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/api && python -m pytest tests/test_pubg_rate_limit.py -v`
Expected: FAIL — `ImportError: cannot import name '_TokenBucket'`.

- [ ] **Step 4: Add the config field**

In `apps/api/src/moneymatch_api/config.py`, after `pubg_api_key`:

```python
    pubg_api_key: str | None = None
    # PUBG's public limit is ~10 req/min. A process-local token bucket in the PUBG
    # host client throttles to this (keep headroom under 10). Caveat: API and
    # worker are separate processes, each with its own bucket — PUBG traffic is
    # worker-dominated, so a conservative per-process budget stays under the cap.
    pubg_rate_limit_per_min: int = 9
```

- [ ] **Step 5: Add the limiter and wire it into every request**

In `apps/api/src/moneymatch_api/services/hosts/pubg.py`, add imports at the top:

```python
import asyncio
import time
```

(`time` is already imported — keep one.) Add the bucket + accessor near the cache globals:

```python
class _TokenBucket:
    """Async token bucket: `capacity` tokens, refilled continuously at
    `capacity/60` per second. `acquire()` blocks until a token is free. The lock
    is held across the wait so waiters are served in order."""

    def __init__(self, rate_per_min: int) -> None:
        self._capacity = float(max(1, rate_per_min))
        self._tokens = self._capacity
        self._refill_per_sec = self._capacity / 60.0
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity,
                    self._tokens + (now - self._updated) * self._refill_per_sec,
                )
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self._tokens) / self._refill_per_sec)


_bucket: _TokenBucket | None = None


def _rate_limiter() -> _TokenBucket:
    global _bucket
    if _bucket is None:
        _bucket = _TokenBucket(get_settings().pubg_rate_limit_per_min)
    return _bucket


def reset_rate_limiter() -> None:
    """Drop the process bucket (tests / config reload)."""
    global _bucket
    _bucket = None
```

In each of `get_player_by_name`, `get_player_by_id`, `get_lifetime`, and `get_match`, add `await _rate_limiter().acquire()` on the line immediately **before** the `await request_json(...)` call (i.e. after the `_api_key()` / cache checks, so no-key and cache-hit paths never consume a token). Example for `get_match`:

```python
    if not _api_key():
        return None
    await _rate_limiter().acquire()
    try:
        response = await request_json(
```

- [ ] **Step 6: Run to verify pass**

Run: `cd apps/api && python -m pytest tests/test_pubg_rate_limit.py tests/test_pubg_settlement.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/moneymatch_api/config.py \
        apps/api/src/moneymatch_api/services/hosts/pubg.py \
        apps/api/tests/conftest.py apps/api/tests/test_pubg_rate_limit.py
git commit -m "feat(pubg): process-local rate limiter on the host client"
```

---

## Task 4: Adapter — official-mode filter, raised fan-out, early-exit (Issues 1/3/4)

**Files:**
- Modify: `apps/api/src/moneymatch_api/constants.py`
- Modify: `apps/api/src/moneymatch_api/adapters/pubg.py`
- Test: `apps/api/tests/test_pubg_adapter.py`

- [ ] **Step 1: Add constants**

In `apps/api/src/moneymatch_api/constants.py`, near the PUBG metric config (after `GAME_HISTORY_FLOOR`):

```python
# PUBG per-poll match fan-out cap. Bootstrap needs ≥ METRIC_PROVISIONAL_MIN_N
# graded samples to lift a stat duel out of "provisional"; 15 clears 10 even
# after custom/event matches are filtered out. Settlement stays cheap via the
# poll's newest-first early-exit + the finished-match cache.
PUBG_MATCH_FANOUT = 15

# Official PUBG modes eligible to settle money. Everything else — custom games,
# arcade, war/zombie, event, training — is excluded so only standard
# battle-royale play grades a duel.
PUBG_OFFICIAL_GAME_MODES: frozenset[str] = frozenset(
    {"solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"}
)
PUBG_OFFICIAL_MATCH_TYPES: frozenset[str] = frozenset({"official", "competitive"})
```

- [ ] **Step 2: Update the test fixtures + add mode/fan-out tests**

In `apps/api/tests/test_pubg_adapter.py`:

Fix the stale module docstring (lines 3-4) — replace "The adapter is dormant (not in the registry yet), so these exercise it directly." with:

```python
The adapter is registered (`pubg.steam`); these exercise it directly against
respx-mocked PUBG API responses — no live network.
```

Update `_match(...)` so fixtures look like real official matches (add `matchType`/`isCustomMatch`):

```python
def _match(
    match_id,
    *,
    kills,
    headshots,
    damage,
    win_place,
    created="2026-07-24T00:00:00Z",
    game_mode="squad-fpp",
    match_type="official",
    is_custom=False,
):
    return {
        "data": {
            "id": match_id,
            "attributes": {
                "gameMode": game_mode,
                "matchType": match_type,
                "isCustomMatch": is_custom,
                "createdAt": created,
            },
        },
        "included": [
            {"type": "roster", "attributes": {}},
            {
                "type": "participant",
                "attributes": {
                    "stats": {
                        "playerId": ACCOUNT,
                        "kills": kills,
                        "headshotKills": headshots,
                        "damageDealt": damage,
                        "winPlace": win_place,
                    }
                },
            },
        ],
    }
```

Add new tests at the end of the file:

```python
@respx.mock
async def test_poll_skips_custom_and_event_matches(pubg_key):
    respx.get(f"{SHARD}/players/{ACCOUNT}").mock(
        return_value=httpx.Response(
            200, json={"data": _player(["official", "custom", "event"])}
        )
    )
    respx.get(f"{SHARD}/matches/official").mock(
        return_value=httpx.Response(
            200, json=_match("official", kills=5, headshots=2, damage=500.0, win_place=1)
        )
    )
    respx.get(f"{SHARD}/matches/custom").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "custom", kills=9, headshots=9, damage=999.0, win_place=1, is_custom=True
            ),
        )
    )
    respx.get(f"{SHARD}/matches/event").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "event",
                kills=9,
                headshots=9,
                damage=999.0,
                win_place=1,
                game_mode="normal-squad",
                match_type="event",
            ),
        )
    )
    from moneymatch_api.adapters.base import GameFilters

    games = await ADAPTER.poll_eligible_games(ACCOUNT, 0, GameFilters())
    assert [g.id for g in games] == ["official"]  # custom + event excluded


@respx.mock
async def test_poll_early_exits_on_first_out_of_window_match(pubg_key):
    # Newest-first list: once a match older than since_ms is hit, stop fetching.
    respx.get(f"{SHARD}/players/{ACCOUNT}").mock(
        return_value=httpx.Response(200, json={"data": _player(["new", "old", "older"])})
    )
    new_route = respx.get(f"{SHARD}/matches/new").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "new", kills=3, headshots=1, damage=300.0, win_place=2,
                created="2026-07-24T00:00:00Z",
            ),
        )
    )
    old_route = respx.get(f"{SHARD}/matches/old").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "old", kills=1, headshots=0, damage=100.0, win_place=8,
                created="2026-07-20T00:00:00Z",
            ),
        )
    )
    older_route = respx.get(f"{SHARD}/matches/older").mock(
        return_value=httpx.Response(
            200,
            json=_match(
                "older", kills=1, headshots=0, damage=100.0, win_place=8,
                created="2026-07-10T00:00:00Z",
            ),
        )
    )
    from moneymatch_api.adapters.base import GameFilters

    since = _ms("2026-07-23T00:00:00Z")
    games = await ADAPTER.poll_eligible_games(ACCOUNT, since, GameFilters())
    assert [g.id for g in games] == ["new"]
    assert new_route.called and old_route.called
    assert not older_route.called  # early-exit: never fetched the 3rd match


def _ms(iso: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/api && python -m pytest tests/test_pubg_adapter.py -k "custom_and_event or early_exits" -v`
Expected: FAIL — event/custom not filtered; `older` match still fetched.

- [ ] **Step 4: Implement the adapter changes**

In `apps/api/src/moneymatch_api/adapters/pubg.py`:

Update imports:

```python
from ..constants import (
    PUBG_MATCH_FANOUT,
    PUBG_OFFICIAL_GAME_MODES,
    PUBG_OFFICIAL_MATCH_TYPES,
)
from ..schemas.profile import ProfileSnapshot
from ..services.hosts import pubg
from ..services.hosts.errors import HostNotConfigured
from .base import GameAdapter, GameFilters, NormGame, TelemetrySample
```

Delete the local `_MATCH_LIMIT = 8` block. Add `defer_bootstrap` to the class:

```python
class PubgAdapter(GameAdapter):
    id = "pubg.steam"
    # PUBG's ~10 req/min budget makes a link-time history bootstrap too expensive
    # to run inline; the settlement worker bootstraps the metric models instead.
    defer_bootstrap = True
```

Replace the `poll_eligible_games` fetch loop with the early-exit version:

```python
        out: list[NormGame] = []
        for match_id in match_ids[:PUBG_MATCH_FANOUT]:
            match = await pubg.get_match(match_id, self._shard)
            if not match:
                continue
            norm = self._normalize(match, account_id)
            if norm is None:
                continue  # unreadable or a non-official mode — skip, keep scanning
            if norm.created_at_ms < since_ms:
                # The match list is newest-first, so everything past here is older.
                break
            out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first
        return out
```

Add the official-mode gate at the top of `_normalize`, and a static helper:

```python
    def _normalize(self, match: dict, account_id: str) -> NormGame | None:
        """Turn a raw match document into a NormGame for ``account_id``."""
        data = match.get("data") or {}
        attrs = data.get("attributes") or {}
        if not self._is_official(attrs):
            return None  # custom / arcade / war / event / training don't settle
        stats = self._participant_stats(match, account_id)
        if stats is None:
            return None
        # ... rest unchanged (kills/metrics/NormGame) ...
```

```python
    @staticmethod
    def _is_official(attrs: dict) -> bool:
        """Only standard battle-royale play settles: an allowlisted gameMode, an
        official/competitive matchType, and not a custom lobby."""
        if attrs.get("isCustomMatch"):
            return False
        game_mode = str(attrs.get("gameMode") or "")
        match_type = str(attrs.get("matchType") or "")
        return (
            game_mode in PUBG_OFFICIAL_GAME_MODES
            and match_type in PUBG_OFFICIAL_MATCH_TYPES
        )
```

Note in the module docstring that `NormGame.speed` carries the `gameMode` (the audit trail for which mode settled), and that team-mode win attribution + cross-mode stat comparison are accepted residuals.

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/api && python -m pytest tests/test_pubg_adapter.py -v`
Expected: PASS (all — updated fixtures + new tests).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/moneymatch_api/constants.py \
        apps/api/src/moneymatch_api/adapters/pubg.py \
        apps/api/tests/test_pubg_adapter.py
git commit -m "feat(pubg): official-mode filter, fan-out 15, newest-first early-exit"
```

---

## Task 5: Deferred bootstrap seam + column + worker sweep (Issue 1, Block C)

**Files:**
- Modify: `apps/api/src/moneymatch_api/adapters/base.py:54-61`
- Modify: `apps/api/src/moneymatch_api/models/linked_account.py`
- Create: `apps/api/migrations/versions/0019_link_bootstrap_at.py`
- Modify: `apps/api/src/moneymatch_api/services/linking_service.py`
- Modify: `apps/api/src/moneymatch_api/workers/settlement_worker.py`
- Test: `apps/api/tests/test_links_endpoints.py`, `apps/api/tests/test_metric_models_service.py`

- [ ] **Step 1: Add `defer_bootstrap` to the adapter base**

In `apps/api/src/moneymatch_api/adapters/base.py`, in `GameAdapter`, after `brokered`:

```python
    id: str
    brokered: bool = False
    # True ⇒ linking must NOT bootstrap this game's metric models inline (its host
    # is too rate-limited for a synchronous history fan-out). The settlement worker
    # bootstraps deferred accounts out-of-band. Default False (bootstrap at link).
    defer_bootstrap: bool = False
```

- [ ] **Step 2: Add the model column**

In `apps/api/src/moneymatch_api/models/linked_account.py`:

Add imports:

```python
from datetime import datetime
```

and add `DateTime` to the sqlalchemy import:

```python
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
```

Add the column after `status`:

```python
    # When this account's metric models were bootstrapped. NULL = "bootstrap
    # still owed": deferred-host links (PUBG) leave it NULL for the worker to
    # claim; cheap hosts bootstrap inline at link and stamp it immediately.
    models_bootstrapped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
```

- [ ] **Step 3: Write the migration**

Create `apps/api/migrations/versions/0019_link_bootstrap_at.py`:

```python
"""linked_accounts.models_bootstrapped_at

NULL means "metric-model bootstrap still owed". Deferred-host links (PUBG) leave
it NULL for the settlement worker to claim; cheap hosts bootstrap inline at link
and are stamped immediately. Existing rows are backfilled to now() so historical
accounts (already bootstrapped under the old code) aren't re-swept.

Revision ID: 0019_link_bootstrap_at
Revises: 0018_risk_flag_pair_cap
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_link_bootstrap_at"
down_revision: str | None = "0018_risk_flag_pair_cap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "linked_accounts",
        sa.Column("models_bootstrapped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE linked_accounts SET models_bootstrapped_at = now()")


def downgrade() -> None:
    op.drop_column("linked_accounts", "models_bootstrapped_at")
```

- [ ] **Step 4: Defer the bootstrap in `bind()` and `refresh()`**

In `apps/api/src/moneymatch_api/services/linking_service.py`, add imports:

```python
from datetime import UTC, datetime
```

In `bind()`, replace the single bootstrap call (line ~187) with:

```python
    adapter = registry.get(game)
    if adapter.defer_bootstrap:
        # Expensive host (PUBG ~10 req/min): the worker bootstraps out-of-band so
        # linking stays fast and never trips the rate limit. Left NULL = owed.
        link.models_bootstrapped_at = None
    else:
        await metric_models_service.bootstrap(session, user.id, game, host_account_id)
        link.models_bootstrapped_at = datetime.now(UTC)
```

In `refresh()`, replace the bootstrap call (line ~234), reusing the `adapter` already fetched at line ~217:

```python
    if adapter.defer_bootstrap:
        link.models_bootstrapped_at = None  # worker re-bootstraps out-of-band
    else:
        await metric_models_service.bootstrap(
            session, user.id, game, link.host_account_id
        )
        link.models_bootstrapped_at = datetime.now(UTC)
```

- [ ] **Step 5: Write the worker-sweep test**

Add to `apps/api/tests/test_metric_models_service.py` (it already has `create_user` + DB session). Append:

```python
import respx
import httpx

from moneymatch_api.config import get_settings
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.services.hosts import pubg
from moneymatch_api.workers import settlement_worker


@respx.mock
async def test_worker_bootstraps_pending_pubg_link(session, new_sessionmaker, monkeypatch):
    monkeypatch.setattr(get_settings(), "pubg_api_key", "test-key")
    pubg.clear_match_cache()
    user = await create_user(session)
    account = "account.pending"
    link = LinkedAccount(
        user_id=user.id,
        game="pubg.steam",
        host_account_id=account,
        host_username="pending",
        models_bootstrapped_at=None,  # bootstrap owed
    )
    session.add(link)
    await session.commit()

    shard = "https://api.pubg.com/shards/steam"
    match_ids = [f"m{i}" for i in range(12)]
    respx.get(f"{shard}/players/{account}").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": account,
                    "attributes": {"name": "pending"},
                    "relationships": {
                        "matches": {
                            "data": [{"type": "match", "id": m} for m in match_ids]
                        }
                    },
                }
            },
        )
    )
    for i, m in enumerate(match_ids):
        respx.get(f"{shard}/matches/{m}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": m,
                        "attributes": {
                            "gameMode": "squad-fpp",
                            "matchType": "official",
                            "isCustomMatch": False,
                            "createdAt": f"2026-07-{i + 1:02d}T00:00:00Z",
                        },
                    },
                    "included": [
                        {
                            "type": "participant",
                            "attributes": {
                                "stats": {
                                    "playerId": account,
                                    "kills": 4 + i,
                                    "headshotKills": 1,
                                    "damageDealt": 300.0 + i,
                                    "winPlace": 1 if i % 2 else 5,
                                }
                            },
                        }
                    ],
                },
            )
        )

    count = await settlement_worker._bootstrap_pending_models(new_sessionmaker)
    assert count == 1

    model = await svc._get_model(session, user.id, "pubg.steam", "pubg_kills") \
        if hasattr(svc, "_get_model") else None
    # Assert via a fresh query instead (svc has no public getter):
    from moneymatch_api.models.skill import MetricModel
    from sqlalchemy import select
    n = await session.scalar(
        select(MetricModel.n).where(
            MetricModel.user_id == user.id,
            MetricModel.game == "pubg.steam",
            MetricModel.metric == "pubg_kills",
        )
    )
    assert n is not None and n >= 10  # Issue 1: stat duels no longer provisional
    refreshed = await session.get(LinkedAccount, link.id)
    await session.refresh(refreshed)
    assert refreshed.models_bootstrapped_at is not None  # stamped once
```

(Remove the dead `model = ...` line if it complicates; the fresh `MetricModel` query is the real assertion.)

- [ ] **Step 6: Run to verify failure**

Run: `cd apps/api && python -m pytest tests/test_metric_models_service.py::test_worker_bootstraps_pending_pubg_link -v`
Expected: FAIL — `AttributeError: module 'settlement_worker' has no attribute '_bootstrap_pending_models'`.

- [ ] **Step 7: Implement the worker sweep**

In `apps/api/src/moneymatch_api/workers/settlement_worker.py`:

Add imports:

```python
from ..adapters import registry
from ..models.linked_account import LinkedAccount
from ..models.skill import MetricModel
```

Add the sweep near the nightly helpers:

```python
_BOOTSTRAP_BATCH_PER_CYCLE = 1


def _deferred_bootstrap_games() -> list[str]:
    return [gid for gid in registry.all_ids() if registry.get(gid).defer_bootstrap]


async def _bootstrap_pending_models(
    sm: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> int:
    """Bootstrap metric models for freshly-linked accounts on deferred hosts
    (PUBG) that left `models_bootstrapped_at` NULL. One account per call keeps
    host calls under the rate limit; the account is stamped so it's done once. If
    the account already has models (seeded/demo), just stamp — never clobber."""
    now = now or _now()
    deferred = _deferred_bootstrap_games()
    if not deferred:
        return 0
    async with sm() as session:
        ids = list(
            await session.scalars(
                select(LinkedAccount.id)
                .where(
                    LinkedAccount.status == "active",
                    LinkedAccount.game.in_(deferred),
                    LinkedAccount.models_bootstrapped_at.is_(None),
                )
                .order_by(LinkedAccount.created_at)
                .limit(_BOOTSTRAP_BATCH_PER_CYCLE)
            )
        )
    done = 0
    for link_id in ids:
        async with sm() as session:
            link = await session.get(LinkedAccount, link_id)
            if link is None or link.models_bootstrapped_at is not None:
                continue
            has_models = await session.scalar(
                select(MetricModel.user_id)
                .where(
                    MetricModel.user_id == link.user_id,
                    MetricModel.game == link.game,
                )
                .limit(1)
            )
            try:
                if has_models is None:
                    await metric_models_service.bootstrap(
                        session, link.user_id, link.game, link.host_account_id
                    )
                link.models_bootstrapped_at = now
                await session.commit()
                done += 1
            except Exception:  # noqa: BLE001 — host hiccup: retry next cycle
                await session.rollback()
                log.warning(
                    "bootstrap.pending_failed", link_id=str(link_id), exc_info=True
                )
    return done
```

Wire it into `run_forever` (NOT `run_cycle`), right after `await maybe_run_nightly(sm)`:

```python
            await maybe_run_nightly(sm)
            await _bootstrap_pending_models(sm)
```

- [ ] **Step 8: Run to verify pass**

Run: `cd apps/api && python -m pytest tests/test_metric_models_service.py -v`
Expected: PASS.

- [ ] **Step 9: Verify the link endpoint still binds a PUBG account (deferred)**

Run: `cd apps/api && python -m pytest tests/test_links_endpoints.py -v`
Expected: PASS. If a test asserted models exist immediately after linking PUBG, update it to assert `models_bootstrapped_at is None` (bootstrap now deferred). Fix any such assertion in `test_links_endpoints.py`, keeping non-deferred games (they still bootstrap inline).

- [ ] **Step 10: Commit**

```bash
git add apps/api/src/moneymatch_api/adapters/base.py \
        apps/api/src/moneymatch_api/models/linked_account.py \
        apps/api/migrations/versions/0019_link_bootstrap_at.py \
        apps/api/src/moneymatch_api/services/linking_service.py \
        apps/api/src/moneymatch_api/workers/settlement_worker.py \
        apps/api/tests/test_metric_models_service.py \
        apps/api/tests/test_links_endpoints.py
git commit -m "feat(pubg): defer metric bootstrap to the worker (unblocks stat duels)"
```

---

## Task 6: Verify demo + matchmaking (Issue 1 end-to-end)

**Files:**
- Verify: `apps/api/src/moneymatch_api/routers/demo.py` (no change expected)
- Test: run demo + matchmaking suites

- [ ] **Step 1: Confirm demo PUBG models stay non-provisional**

Demo seeds `pubg_kills/pubg_damage/pubg_headshot_pct` with `n = _DEMO_METRIC_N (25)` (`routers/demo.py`), independent of bootstrap. The worker sweep skips accounts that already have models (Step 7 `has_models`), so demo models are never clobbered.

Run: `cd apps/api && python -m pytest tests/test_getting_started.py tests/test_demo_reset.py tests/test_demo_relink.py -v`
Expected: PASS.

- [ ] **Step 2: Confirm a PUBG stat duel with n≥10 is accepted by matchmaking**

Run: `cd apps/api && python -m pytest tests/test_matchmaking.py -v`
Expected: PASS. If there is no PUBG stat-duel case, add one mirroring the existing CS2 provisional test: seed a `MetricModel(game="pubg.steam", metric="pubg_kills", n=12)` for a user with a linked PUBG account and assert enqueuing the `kills` market does NOT raise `metric_provisional` (and that `n=5` still does).

- [ ] **Step 3: Commit any test additions**

```bash
git add apps/api/tests/test_matchmaking.py
git commit -m "test(pubg): stat duel accepted once n≥10"
```

(Skip if no file changed.)

---

## Task 7: Lower-severity notes

**Files:**
- Create: `apps/api/migrations/versions/0020_seed_pubg_flag.py`
- Modify: `apps/api/src/moneymatch_api/adapters/pubg.py` (link message + kd comment)

- [ ] **Step 1: Seed the PUBG feature flag (idempotent migration)**

Create `apps/api/migrations/versions/0020_seed_pubg_flag.py`:

```python
"""Seed the game:pubg.steam feature flag.

The initial migration hard-coded only chess/cs2/dota2. PUBG defaults to enabled
(absent flag ⇒ on), but seeding the row gives admin a toggle target and matches
the "seed each game flag in a migration" convention. Idempotent.

Revision ID: 0020_seed_pubg_flag
Revises: 0019_link_bootstrap_at
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_seed_pubg_flag"
down_revision: str | None = "0019_link_bootstrap_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO feature_flags (key, enabled, payload) "
        "VALUES ('game:pubg.steam', true, '{}'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'game:pubg.steam'")
```

- [ ] **Step 2: Improve the link "not found" message + clarify the kd formula**

In `apps/api/src/moneymatch_api/adapters/pubg.py`, `link_account`:

```python
        if player is None:
            raise ValueError(
                f"PUBG player '{identifier}' not found — names are case-sensitive; "
                "check the exact spelling and platform."
            )
```

In `_profile_from`, above the `kd = ...` line, add:

```python
        # PUBG's conventional K/D: kills per non-winning round (losses = rounds −
        # wins), NOT kills/deaths. A soft profile/bracketing signal only.
        kd = (agg["kills"] / losses) if losses else agg["kills"]
```

- [ ] **Step 3: Verify existing link tests still match the message**

Run: `cd apps/api && python -m pytest tests/test_pubg_adapter.py -k "unknown_player or not_found" -v`
Expected: PASS (the test matches on `"not found"`, still a substring).

- [ ] **Step 4: Apply the migrations against the dev DB and confirm they chain**

Run: `cd apps/api && alembic upgrade head`
Expected: `0019_link_bootstrap_at` then `0020_seed_pubg_flag` applied, no error. (Uses the dev DB URL; see the Render/free-tier migration note if running against the external DB.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/migrations/versions/0020_seed_pubg_flag.py \
        apps/api/src/moneymatch_api/adapters/pubg.py
git commit -m "chore(pubg): seed feature flag, case-sensitivity hint, kd comment"
```

---

## Task 8: Full verification

- [ ] **Step 1: Run the whole API suite**

Run: `cd apps/api && python -m pytest -q`
Expected: all green (settlement-invariant suites are the spec — they must not regress).

- [ ] **Step 2: Lint / format (repo pre-commit)**

Run: `cd /Users/shreyansh/Desktop/moneymatch && ruff check apps/api && ruff format --check apps/api`
Expected: clean (run `ruff format apps/api` + `ruff check --fix apps/api` if needed, then re-commit).

- [ ] **Step 3: Final commit if formatting changed**

```bash
git add -A && git commit -m "style: ruff format for pubg-completion" || true
```

---

## Self-Review

**Spec coverage:**
- Issue 1 (stat duels blocked) → Task 4 (fan-out 15) + Task 5 (deferred worker bootstrap → n≥10) + Task 6 (verify). ✅
- Issue 2 (outage swallowing) → Task 2 (propagate in `get_player_by_id`/`get_match`) + `test_pubg_settlement.py`. ✅
- Issue 3 (rate limit / 429) → Task 1 (429→`HostRateLimited`) + Task 3 (limiter) + Task 4 (early-exit). ✅
- Issue 4 (mode filter) → Task 4 (`_is_official`, allowlists). ✅
- Blocks A/B/C → Tasks 1 / 3 / 5. ✅
- Lower-severity notes → Task 7 (flag seed, link message, kd comment) + Task 4 (docstring). ✅

**Deliberate deviations from the spec (flagged honestly):**
- The spec mentioned "record `gameMode` in the stored stat-line detail." To avoid touching the shared grading `_decide`/`_player_result` path, the mode audit trail is `NormGame.speed` (already set to `gameMode`), not a new stat-line field. Same information, no shared-code change.
- The bootstrap sweep lives in `run_forever` (not `run_cycle`), mirroring `maybe_run_nightly`, so the many `run_cycle`-based tests are unaffected and the money path stays untouched. It also skips accounts that already have models, so demo/test-seeded PUBG accounts are never clobbered.

**Placeholder scan:** none — every code step shows real code and the exact command + expected output.

**Type/name consistency:** `HostRateLimited` (Tasks 1/2), `_TokenBucket`/`_rate_limiter`/`reset_rate_limiter` (Task 3), `PUBG_MATCH_FANOUT`/`PUBG_OFFICIAL_GAME_MODES`/`PUBG_OFFICIAL_MATCH_TYPES` (Task 4), `defer_bootstrap` (Tasks 4/5), `models_bootstrapped_at` (Task 5), `_bootstrap_pending_models` (Task 5) are used consistently across tasks.

**Not needed:** `make gen-api` — no API schema/market changes (the PUBG markets already exist).
