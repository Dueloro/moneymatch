"""Solo-pool engine: personal bars, room formation with the composition predicate,
byte-for-byte room-bar reproducibility, the anti-collusion gates, and the
settlement invariant on every branch.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.constants import POOL_DIFFICULTY_K
from moneymatch_api.models.pools import SoloEntry, SoloPool
from moneymatch_api.services import (
    fairness,
    metric_models_service,
    pool_engine,
    reconciliation_service,
    wallet_service,
)
from moneymatch_api.services.pool_engine import PoolError, PoolGrade

from .factories import (
    chess_moves_corrected,
    chess_profile,
    create_linked_account,
    create_metric_model,
    create_user,
    create_wallet,
)

pytestmark = pytest.mark.asyncio

CHESS = "chess.lichess"
METRIC = "chess_moves"


class _FakeAdapter:
    id = CHESS

    async def poll_eligible_games(self, host, since_ms, filters):
        return []


@pytest.fixture(autouse=True)
def _stub_host(monkeypatch):
    from moneymatch_api.adapters import registry

    monkeypatch.setattr(registry, "get", lambda game_id: _FakeAdapter())


async def pool_player(session, name, *, mu, sigma=8.0, n=15, fund=10_000):
    user = await create_user(session, username=name)
    link = await create_linked_account(
        session,
        user,
        CHESS,
        host_account_id=f"host_{name}",
        profile=chess_profile(name),
    )
    await create_metric_model(session, user, CHESS, METRIC, mu=mu, sigma=sigma, n=n)
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user, link


async def enq(session, user, *, difficulty="medium", entry=1000):
    return await pool_engine.enqueue(
        session,
        user,
        game=CHESS,
        metric=METRIC,
        difficulty=difficulty,
        entry_cents=entry,
    )


def _bar(mu, sigma, k):
    return fairness.personal_bar(mu, sigma, k, 1.0, True, positive=True, floor=2.0)


async def _bal(session, user):
    w = await wallet_service.get_wallet(session, user.id)
    return w.available_cents, w.escrow_cents


async def test_preview_quotes_bars_from_own_baseline(session):
    user, _ = await pool_player(session, "u", mu=34.0, sigma=8.0)
    preview = await pool_engine.preview_bars(session, user, CHESS, METRIC)
    assert preview["provisional"] is False
    by_diff = {c["difficulty"]: c for c in preview["cards"]}
    bars = {d: c["bar"] for d, c in by_diff.items()}
    assert bars == {"easy": 28.0, "medium": 25.0, "hard": 22.0}
    mu, sigma = chess_moves_corrected(34.0, 8.0, 15)

    # Disclosed clear rates, not odds: the rate shown is the one implied by the bar
    # actually quoted (rounded to whole moves), not the nominal 1 − Φ(k).
    medium = by_diff["medium"]
    assert medium["clear_rate"] == pytest.approx(
        fairness.clear_prob(medium["bar"], mu, sigma, True, positive=True), abs=1e-4
    )
    # And rounding is the only thing moving it: still near the design rate.
    assert medium["clear_rate"] == pytest.approx(
        fairness.p_target_for_k(POOL_DIFFICULTY_K["medium"]), abs=0.02
    )


async def test_sparse_history_can_now_enter(session):
    user, _ = await pool_player(session, "rookie", mu=34.0, n=4)
    preview = await pool_engine.preview_bars(session, user, CHESS, METRIC)
    assert preview["provisional"] is False and preview["cards"]
    result = await enq(session, user)
    assert result.status in ("searching", "formed")


async def test_no_baseline_cannot_enter(session):
    user, _ = await pool_player(session, "blank", mu=34.0, n=0)
    with pytest.raises(PoolError) as exc:
        await enq(session, user)
    assert exc.value.code == "no_stat_baseline"


async def test_room_forms_at_size_with_derived_room_bar(session):
    users = []
    for i, mu in enumerate([34.0, 35.0, 36.0, 35.0]):
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
    expected = fairness.room_bar([e.personal_bar for e in entries], 1.0)
    assert pool.room_bar == expected
    for u in users:
        assert (await _bal(session, u))[1] == 1000


async def test_cannot_dismiss_a_formed_room(session):
    users = []
    for i, mu in enumerate([34.0, 35.0, 36.0, 35.0]):
        u, _ = await pool_player(session, f"r{i}", mu=mu)
        users.append(u)
    for u in users[:3]:
        await enq(session, u)
    assert (await enq(session, users[3])).status == "formed"
    assert await pool_engine.cancel(session, users[0]) is False
    assert (await _bal(session, users[0]))[1] == 1000


async def test_room_bar_reproduces_byte_for_byte_from_snapshots(session):
    users = []
    for i, mu in enumerate([34.0, 35.0, 36.0, 35.0]):
        u, _ = await pool_player(session, f"p{i}", mu=mu)
        users.append(u)
    for u in users[:3]:
        await enq(session, u)
    pool = (await enq(session, users[3])).pool

    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    redrawn_bars = [
        _bar(
            e.baseline_snapshot["mu"],
            e.baseline_snapshot["sigma"],
            POOL_DIFFICULTY_K["medium"],
        )
        for e in entries
    ]
    assert redrawn_bars == [e.personal_bar for e in entries]
    assert fairness.room_bar(redrawn_bars, 1.0) == pool.room_bar


async def test_composition_refuses_a_shark(session):
    for i, mu in enumerate([35.0, 36.0, 34.0]):
        u, _ = await pool_player(session, f"p{i}", mu=mu)
        await enq(session, u)
    shark, _ = await pool_player(session, "shark", mu=12.0, sigma=3.0, n=60)
    result = await enq(session, shark)
    assert result.status == "searching"
    count = await session.scalar(select(SoloPool.id))
    assert count is None


async def test_baseline_frozen_against_model_refresh(session):
    u1, _ = await pool_player(session, "a", mu=34.0)
    await enq(session, u1)
    frozen = (await pool_engine.get_waiting_ticket(session, u1.id)).personal_bar
    model = await metric_models_service.get_metric_model(session, u1.id, CHESS, METRIC)
    model.mu = 90.0
    await session.flush()
    ticket = await pool_engine.get_waiting_ticket(session, u1.id)
    assert ticket.personal_bar == frozen


# settlement invariants.


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
    pool, users = await _form_room(session, [35.0, 35.0, 36.0, 34.0])
    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
    )
    # Pool $40, rake 10% of $40 = $4, net $36 / 2 = $18 each.
    grades = {}
    for i, e in enumerate(entries):
        grades[e.user_id] = PoolGrade(
            cleared=(i < 2), telemetry={METRIC: 20.0 if i < 2 else 60.0}
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
    pool, users = await _form_room(session, [35.0, 35.0, 36.0, 34.0])
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
    pool, users = await _form_room(session, [35.0, 35.0, 36.0, 34.0])
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
