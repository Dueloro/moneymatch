"""Settlement worker: adapter-mocked grading of each result branch, the money
invariant after every settle, SKIP-LOCKED re-claimability, window extension on
host outage, and the kill switches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from moneymatch_api.adapters import registry
from moneymatch_api.constants import (
    FLAG_QUEUE_PAUSED,
    FLAG_SETTLEMENT_PAUSED,
    GAME_CHESS_LICHESS,
)
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
from .test_matchmaking import chess_player, enq_chess

pytestmark = pytest.mark.asyncio


class FakeChessAdapter:
    id = GAME_CHESS_LICHESS

    def __init__(self, winner: str | None = None, *, raise_host=False):
        self.winner = winner
        self.raise_host = raise_host

    async def match_winner(self, game_id, players):
        if self.raise_host:
            raise HostUnavailable("lichess", "down")
        return self.winner

    async def poll_eligible_games(self, host, since_ms, filters):
        return []

    async def live_match(self, game_id, players):
        return None


async def _fund(session, user, amount):
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, amount, memo="fund")


async def setup_active_chess(sm):
    async with sm() as s:
        a = await chess_player(s, "alice", rating=1500)
        b = await chess_player(s, "bob", rating=1510)
        await _fund(s, a, 10_000)
        await _fund(s, b, 10_000)
        await enq_chess(s, a)
        match = (await enq_chess(s, b)).match
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


async def test_win_pays_winner_and_reconciles(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(info["a_host"]))

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.settled == 1
    assert await _match_state(sm, info["match_id"]) == "SETTLED"
    assert await _balance(sm, info["a"]) == (10800, 0)
    assert await _balance(sm, info["b"]) == (9000, 0)

    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", info["match_id"])
        assert recon.ok and recon.totals["rake"] == 200
        assert (
            recon.totals["distributed"] + recon.totals["rake"]
            == recon.totals["entries"]
        )
        assert (await reconciliation_service.check_all(s)).ok
        m = await s.get(Match, info["match_id"])
        assert m.winner_user_id == info["a"]
        assert m.raw_payload_id is not None


async def test_draw_pushes_and_refunds_without_rake(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(""))

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.pushed == 1
    assert await _match_state(sm, info["match_id"]) == "PUSHED"
    assert await _balance(sm, info["a"]) == (10000, 0)  # refunded
    assert await _balance(sm, info["b"]) == (10000, 0)
    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", info["match_id"])
        assert recon.ok and recon.totals["rake"] == 0


async def test_unfinished_game_waits_inside_the_window(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(None))

    report = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert report.pending == 1
    assert await _match_state(sm, info["match_id"]) == "AWAITING_RESULT"
    assert await _balance(sm, info["a"]) == (9000, 1000)


async def test_no_qualifying_game_at_deadline_cancels_and_refunds(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(None))

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
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(raise_host=True))

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
    assert after > before
    assert await _balance(sm, info["a"]) == (9000, 1000)


# SKIP LOCKED re-claimability.


async def test_locked_match_is_skipped_and_stays_claimable(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(info["a_host"]))

    lock_session = new_sessionmaker()()
    async with lock_session as locker:
        # A worker that claimed the row and then crashed mid-settle: the row is locked,
        # uncommitted.
        await locker.execute(
            select(Match).where(Match.id == info["match_id"]).with_for_update()
        )
        report = await settlement_worker.run_cycle(
            sm, now=info["matched_at"] + timedelta(seconds=5)
        )
        assert report.settled == 0
        assert await _match_state(sm, info["match_id"]) == "ACTIVE"

    # Lock released → a subsequent cycle claims and settles it.
    report2 = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=6)
    )
    assert report2.settled == 1


async def test_settlement_paused_halts_the_loop(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter())
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
    assert await _match_state(sm, info["match_id"]) == "ACTIVE"


async def test_queue_paused_drains_waiting_tickets(monkeypatch):
    sm = new_sessionmaker()
    async with sm() as s:
        a = await chess_player(s, "waiter")
        await enq_chess(s, a)
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
        a = await chess_player(s, "waiter")
        await enq_chess(s, a)
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
        a = await chess_player(s, "alice")
        b = await chess_player(s, "bob")
        await _fund(s, a, 10_000)
        await _fund(s, b, 10_000)
        await enq_chess(s, a)
        match = (await enq_chess(s, b)).match
        await match_lifecycle.confirm(s, match, a)
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
