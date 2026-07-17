"""Solo-pool engine: personal bars, room formation with the composition
predicate, byte-for-byte room-bar reproducibility, the anti-collusion gates, and
the settlement invariant on every branch."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.pools import SoloEntry, SoloPool
from moneymatch_api.services import (
    fairness,
    pool_engine,
    reconciliation_service,
    wallet_service,
)
from moneymatch_api.services.pool_engine import PoolError, PoolGrade

from .factories import (
    create_linked_account,
    create_metric_model,
    create_user,
    create_wallet,
    cs2_profile,
)

pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
KD = "cs2_kd_ratio"


class _FakeAdapter:
    """No-network stand-in so the sandbagging detector has nothing to flag."""

    id = CS2
    brokered = False

    async def poll_eligible_games(self, host, since_ms, filters):
        return []


@pytest.fixture(autouse=True)
def _stub_host(monkeypatch):
    from moneymatch_api.adapters import registry

    monkeypatch.setattr(registry, "get", lambda game_id: _FakeAdapter())


async def pool_player(session, name, *, mu, sigma=0.30, n=15, fund=10_000):
    user = await create_user(session, username=name)
    link = await create_linked_account(
        session, user, CS2, host_account_id=f"host_{name}", profile=cs2_profile(name)
    )
    await create_metric_model(session, user, CS2, KD, mu=mu, sigma=sigma, n=n)
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user, link


async def enq(session, user, *, difficulty="medium", entry=1000):
    return await pool_engine.enqueue(
        session, user, game=CS2, metric=KD, difficulty=difficulty, entry_cents=entry
    )


async def _bal(session, user):
    w = await wallet_service.get_wallet(session, user.id)
    return w.available_cents, w.escrow_cents


# --- personal bars -------------------------------------------------------- #


async def test_preview_quotes_bars_from_own_baseline(session):
    user, _ = await pool_player(session, "u", mu=1.50, sigma=0.30)
    preview = await pool_engine.preview_bars(session, user, CS2, KD)
    assert preview["provisional"] is False
    by_diff = {c["difficulty"]: c for c in preview["cards"]}
    # Easy 1.65, Medium 1.80, Hard 2.00 (μ + k·σ rounded to 0.05).
    assert by_diff["easy"]["bar"] == 1.65
    assert by_diff["medium"]["bar"] == 1.80
    # Disclosed clear rates, not odds: 1 − Φ(k).
    assert by_diff["medium"]["clear_rate"] == pytest.approx(
        fairness.p_target_for_k(1.0), abs=1e-3
    )


async def test_provisional_metric_cannot_enter(session):
    user, _ = await pool_player(session, "rookie", mu=1.50, n=4)
    with pytest.raises(PoolError) as exc:
        await enq(session, user)
    assert exc.value.code == "metric_provisional"


# --- room formation ------------------------------------------------------- #


async def test_room_forms_at_size_with_derived_room_bar(session):
    # Four similar players → a Medium room forms; room_bar = round(mean(bars)).
    users = []
    for i, mu in enumerate([1.48, 1.50, 1.52, 1.50]):
        u, _ = await pool_player(session, f"p{i}", mu=mu)
        users.append(u)
    for u in users[:3]:
        assert (await enq(session, u)).status == "searching"
    result = await enq(session, users[3])
    assert result.status == "formed"
    pool = result.pool
    assert pool.room_size == 4 and pool.state == "LOCKED"

    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    expected = fairness.room_bar([e.personal_bar for e in entries], 0.05)
    assert pool.room_bar == expected
    # Everyone escrowed exactly the entry.
    for u in users:
        assert (await _bal(session, u))[1] == 1000


async def test_room_bar_reproduces_byte_for_byte_from_snapshots(session):
    users = []
    for i, mu in enumerate([1.48, 1.50, 1.52, 1.50]):
        u, _ = await pool_player(session, f"p{i}", mu=mu)
        users.append(u)
    for u in users[:3]:
        await enq(session, u)
    pool = (await enq(session, users[3])).pool

    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    # Re-derive each personal bar from the stored baseline, then the room bar.
    redrawn_bars = [
        fairness.personal_bar(
            e.baseline_snapshot["mu"], e.baseline_snapshot["sigma"], 1.0, 0.05
        )
        for e in entries
    ]
    assert redrawn_bars == [e.personal_bar for e in entries]
    assert fairness.room_bar(redrawn_bars, 0.05) == pool.room_bar


async def test_composition_refuses_a_shark(session):
    # Three fair players + one shark (far higher μ) → no fair room forms.
    for i, mu in enumerate([1.50, 1.52, 1.48]):
        u, _ = await pool_player(session, f"p{i}", mu=mu)
        await enq(session, u)
    shark, _ = await pool_player(session, "shark", mu=2.60)
    result = await enq(session, shark)
    assert result.status == "searching"  # shark can't be dragged into the room
    count = await session.scalar(select(SoloPool.id))
    assert count is None  # no pool formed at all


async def test_baseline_frozen_against_model_refresh(session):
    u1, _ = await pool_player(session, "a", mu=1.50)
    await enq(session, u1)  # freezes bar at μ=1.50 → 1.80
    # Refresh the model to something wild after queueing.
    model = await pool_engine._metric_model(session, u1.id, CS2, KD)
    model.mu = 5.0
    await session.flush()
    ticket = await pool_engine.get_waiting_ticket(session, u1.id)
    assert ticket.personal_bar == 1.80  # unchanged (frozen at enqueue)


# --- settlement invariants ------------------------------------------------ #


async def _form_room(session, mus):
    users = []
    for i, mu in enumerate(mus):
        u, _ = await pool_player(session, f"m{i}", mu=mu)
        users.append(u)
    for u in users[:-1]:
        await enq(session, u)
    pool = (await enq(session, users[-1])).pool
    assert pool is not None
    return pool, users


async def test_settle_clearers_split_pool_minus_rake(session):
    pool, users = await _form_room(session, [1.50, 1.50, 1.52, 1.48])
    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    # Two clear, two miss. Pool $40, rake 10% of $40 = $4, net $36 / 2 = $18 each.
    grades = {}
    for i, e in enumerate(entries):
        grades[e.user_id] = PoolGrade(
            cleared=(i < 2), telemetry={KD: 2.0 if i < 2 else 0.1}
        )
    await pool_engine.settle_pool(session, pool, grades)
    assert pool.state == "SETTLED"
    cleared = [e for e in entries if e.status == "CLEARED"]
    assert len(cleared) == 2 and all(e.payout_cents == 1800 for e in cleared)
    assert pool.rake_cents == 400
    recon = await reconciliation_service.check(session, "solo_pool", pool.id)
    assert recon.ok
    assert (await reconciliation_service.check_all(session)).ok


async def test_settle_no_clearers_refunds_all_zero_rake(session):
    pool, users = await _form_room(session, [1.50, 1.50, 1.52, 1.48])
    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    grades = {e.user_id: PoolGrade(cleared=False) for e in entries}
    await pool_engine.settle_pool(session, pool, grades)
    assert pool.rake_cents == 0
    for u in users:
        assert (await _bal(session, u)) == (10000, 0)  # fully refunded
    recon = await reconciliation_service.check(session, "solo_pool", pool.id)
    assert recon.ok and recon.totals["rake"] == 0


async def test_settle_unverifiable_refunded_off_the_top(session):
    pool, users = await _form_room(session, [1.50, 1.50, 1.52, 1.48])
    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    # One clears, two miss, one unverifiable (refunded before the split).
    grades = {}
    for i, e in enumerate(entries):
        cleared = True if i == 0 else (None if i == 3 else False)
        grades[e.user_id] = PoolGrade(cleared=cleared)
    await pool_engine.settle_pool(session, pool, grades)
    by_status = {e.status for e in entries}
    assert "REFUNDED" in by_status and "CLEARED" in by_status
    # Distributable = 3 entries × $10 = $30; rake $3; winner takes $27.
    winner = next(e for e in entries if e.status == "CLEARED")
    assert winner.payout_cents == 2700
    assert pool.rake_cents == 300
    recon = await reconciliation_service.check(session, "solo_pool", pool.id)
    assert recon.ok


async def test_cancel_pool_refunds_all(session):
    pool, users = await _form_room(session, [1.50, 1.50, 1.52, 1.48])
    await pool_engine.cancel_pool(session, pool, reason="test")
    assert pool.state == "CANCELED" and pool.rake_cents == 0
    for u in users:
        assert (await _bal(session, u)) == (10000, 0)
    recon = await reconciliation_service.check(session, "solo_pool", pool.id)
    assert recon.ok
