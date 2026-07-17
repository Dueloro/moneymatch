"""Settlement worker: adapter-mocked grading of each market branch, the money
invariant after every settle, SKIP-LOCKED re-claimability, window extension on
host outage, and the kill switches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.constants import FLAG_QUEUE_PAUSED, FLAG_SETTLEMENT_PAUSED
from moneymatch_api.models.feature_flag import FeatureFlag
from moneymatch_api.models.play import Match, QueueTicket
from moneymatch_api.services import (
    match_lifecycle,
    reconciliation_service,
    wallet_service,
)
from moneymatch_api.services.hosts.errors import HostUnavailable
from moneymatch_api.workers import settlement_worker

from .conftest import new_sessionmaker
from .factories import create_wallet
from .test_matchmaking import cs2_player, enq_cs2

pytestmark = pytest.mark.asyncio


class FakeCS2Adapter:
    id = "cs2.faceit"
    brokered = False

    def __init__(self, games_by_host=None, *, raise_host=False):
        self.games_by_host = games_by_host or {}
        self.raise_host = raise_host

    async def poll_eligible_games(self, host, since_ms, filters):
        if self.raise_host:
            raise HostUnavailable("faceit", "down")
        return self.games_by_host.get(host, [])


def _game(created_ms: int, *, won=None, metrics=None) -> NormGame:
    return NormGame(
        id=f"m{created_ms}",
        speed="cs2",
        rated=True,
        created_at_ms=created_ms,
        moves=0,
        won=won,
        drawn=False,
        metrics=metrics or {},
    )


async def _fund(session, user, amount):
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, amount, memo="fund")


async def setup_active_cs2(sm, *, market="kd_ratio"):
    """Two funded CS2 players in an ACTIVE match, committed. Returns match info."""
    async with sm() as s:
        a = await cs2_player(s, "alice", mu=1.0, sigma=0.3)
        b = await cs2_player(s, "bob", mu=1.0, sigma=0.3)
        await _fund(s, a, 10_000)
        await _fund(s, b, 10_000)
        await enq_cs2(s, a, market=market)
        match = (await enq_cs2(s, b, market=market)).match
        await match_lifecycle.confirm(s, match, a)
        await match_lifecycle.confirm(s, match, b)
        await s.commit()
        seats = await match_lifecycle.players(s, match.id)
        host = {seat.user_id: seat.host_account_id for seat in seats}
        return {
            "match_id": match.id,
            "matched_at": match.matched_at,
            "a": a.id,
            "b": b.id,
            "a_host": host[a.id],
            "b_host": host[b.id],
        }


async def _balance(sm, user_id):
    async with sm() as s:
        w = await wallet_service.get_wallet(s, user_id)
        return w.available_cents, w.escrow_cents


async def _match_state(sm, match_id):
    async with sm() as s:
        return await s.scalar(select(Match.state).where(Match.id == match_id))


# --- grading branches ----------------------------------------------------- #


async def test_stat_race_win_pays_winner_and_reconciles(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.settled == 1
    assert await _match_state(sm, info["match_id"]) == "SETTLED"
    assert await _balance(sm, info["a"]) == (10800, 0)  # +$18 prize
    assert await _balance(sm, info["b"]) == (9000, 0)  # −$10 stake

    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", info["match_id"])
        assert recon.ok and recon.totals["rake"] == 200
        assert (await reconciliation_service.check_all(s)).ok
        # Winner's stat line + audit back-ref are stored.
        m = await s.get(Match, info["match_id"])
        assert m.raw_payload_id is not None
        seats = await match_lifecycle.players(s, info["match_id"])
        assert any(
            sp.stat_line and sp.stat_line.get("cs2_kd_ratio") == 1.5 for sp in seats
        )


async def test_stat_race_equal_stat_pushes(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.3})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.3})],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.pushed == 1
    assert await _match_state(sm, info["match_id"]) == "PUSHED"
    assert await _balance(sm, info["a"]) == (10000, 0)  # refunded
    assert await _balance(sm, info["b"]) == (10000, 0)


async def test_win_next_win_beats_loss(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="win_next")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, won=True)],
            info["b_host"]: [_game(ms, won=False)],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.settled == 1
    assert await _balance(sm, info["a"]) == (10800, 0)


async def test_win_next_both_win_pushes(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="win_next")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, won=True)],
            info["b_host"]: [_game(ms, won=True)],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)
    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.pushed == 1


async def test_no_qualifying_game_at_deadline_cancels_and_refunds(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    fake = FakeCS2Adapter({})  # neither played
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    # Past the 24 h window (before the 48 h hard ceiling) → CANCEL + full refund.
    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(hours=25)
    )
    assert report.canceled == 1
    assert await _match_state(sm, info["match_id"]) == "CANCELED"
    assert await _balance(sm, info["a"]) == (10000, 0)
    assert await _balance(sm, info["b"]) == (10000, 0)


async def test_host_outage_extends_window_without_settling(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    monkeypatch.setattr(registry, "get", lambda gid: FakeCS2Adapter(raise_host=True))

    async with sm() as s:
        before = await s.scalar(
            select(Match.window_ends_at).where(Match.id == info["match_id"])
        )

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.pending == 1
    assert await _match_state(sm, info["match_id"]) == "AWAITING_RESULT"
    async with sm() as s:
        after = await s.scalar(
            select(Match.window_ends_at).where(Match.id == info["match_id"])
        )
    assert after > before  # outage did not consume the window
    # No money moved.
    assert await _balance(sm, info["a"]) == (9000, 1000)


# --- SKIP LOCKED re-claimability ------------------------------------------ #


async def test_locked_match_is_skipped_and_stays_claimable(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    fake = FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
        }
    )
    monkeypatch.setattr(registry, "get", lambda gid: fake)

    lock_session = new_sessionmaker()()
    async with lock_session as locker:
        # Simulate a worker that claimed the row and then crashed mid-settle: the
        # row is locked, uncommitted.
        await locker.execute(
            select(Match).where(Match.id == info["match_id"]).with_for_update()
        )
        report = await settlement_worker.run_cycle(
            sm, now=info["matched_at"] + timedelta(seconds=5)
        )
        assert report.settled == 0  # skipped, not lost
        assert await _match_state(sm, info["match_id"]) == "ACTIVE"

    # Lock released → a subsequent cycle claims and settles it.
    report2 = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=6)
    )
    assert report2.settled == 1


# --- kill switches + housekeeping ----------------------------------------- #


async def test_settlement_paused_halts_the_loop(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    monkeypatch.setattr(registry, "get", lambda gid: FakeCS2Adapter())
    async with sm() as s:
        await s.execute(
            update(FeatureFlag)
            .where(FeatureFlag.key == FLAG_SETTLEMENT_PAUSED)
            .values(enabled=True)
        )
        await s.commit()

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.paused is True
    assert await _match_state(sm, info["match_id"]) == "ACTIVE"  # untouched


async def test_queue_paused_drains_waiting_tickets(monkeypatch):
    sm = new_sessionmaker()
    async with sm() as s:
        a = await cs2_player(s, "waiter", mu=1.0, sigma=0.3)
        await enq_cs2(s, a)  # A waits
        await s.execute(
            update(FeatureFlag)
            .where(FeatureFlag.key == FLAG_QUEUE_PAUSED)
            .values(enabled=True)
        )
        await s.commit()

    report = await settlement_worker.run_cycle(sm)
    assert report.drained_tickets == 1
    async with sm() as s:
        state = await s.scalar(
            select(QueueTicket.state).where(QueueTicket.user_id == a.id)
        )
    assert state == "canceled"


async def test_expired_ticket_is_reaped(monkeypatch):
    sm = new_sessionmaker()
    async with sm() as s:
        a = await cs2_player(s, "waiter", mu=1.0, sigma=0.3)
        await enq_cs2(s, a)
        # Backdate the ticket past its TTL.
        await s.execute(
            update(QueueTicket)
            .where(QueueTicket.user_id == a.id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await s.commit()

    report = await settlement_worker.run_cycle(sm)
    assert report.expired_tickets == 1


async def test_expired_pending_match_refunds_the_confirmer(monkeypatch):
    sm = new_sessionmaker()
    async with sm() as s:
        a = await cs2_player(s, "alice", mu=1.0, sigma=0.3)
        b = await cs2_player(s, "bob", mu=1.0, sigma=0.3)
        await _fund(s, a, 10_000)
        await _fund(s, b, 10_000)
        await enq_cs2(s, a)
        match = (await enq_cs2(s, b)).match
        await match_lifecycle.confirm(s, match, a)  # only A escrows → still PENDING
        # Backdate the confirm window.
        await s.execute(
            update(Match)
            .where(Match.id == match.id)
            .values(window_ends_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await s.commit()
        match_id, a_id = match.id, a.id

    report = await settlement_worker.run_cycle(sm)
    assert report.expired_pending == 1
    assert await _match_state(sm, match_id) == "CANCELED"
    assert await _balance(sm, a_id) == (10000, 0)  # refunded
