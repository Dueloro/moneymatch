"""Worker: pool & tournament window settlement from server-fetched telemetry,
raw-payload evidence, the money invariant, boundary exclusion, and the live
standings refresh."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.models.pools import SoloEntry, SoloPool
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import (
    pool_engine,
    reconciliation_service,
    tournament_engine,
    wallet_service,
)
from moneymatch_api.workers import settlement_worker

from .conftest import new_sessionmaker
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


class FakeAdapter:
    """Returns per-host games; used for both the sandbagging poll and grading."""

    id = CS2
    brokered = False

    def __init__(self, games_by_host=None):
        self.games_by_host = games_by_host or {}

    async def poll_eligible_games(self, host, since_ms, filters):
        return self.games_by_host.get(host, [])


def _game(created_ms: int, kd: float) -> NormGame:
    return NormGame(
        id=f"m{created_ms}",
        speed="cs2",
        rated=True,
        created_at_ms=created_ms,
        moves=0,
        won=None,
        drawn=False,
        metrics={KD: kd},
    )


async def _player(session, name, *, mu, fund=10_000, host=None):
    host = host or f"host_{name}"
    user = await create_user(session, username=name)
    await create_linked_account(
        session, user, CS2, host_account_id=host, profile=cs2_profile(name)
    )
    await create_metric_model(session, user, CS2, KD, mu=mu, sigma=0.30, n=15)
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user, host


async def _bal(sm, user_id):
    async with sm() as s:
        w = await wallet_service.get_wallet(s, user_id)
        return w.available_cents, w.escrow_cents


# --------------------------------------------------------------------------- #
# Pools.
# --------------------------------------------------------------------------- #


async def test_pool_settles_from_server_telemetry(monkeypatch):
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())  # no sandbag history
    async with sm() as s:
        users = []
        for i, mu in enumerate([1.50, 1.50, 1.52, 1.48]):
            u, host = await _player(s, f"p{i}", mu=mu)
            users.append((u, host))
        for u, _ in users[:3]:
            await pool_engine.enqueue(
                s, u, game=CS2, metric=KD, difficulty="medium", entry_cents=1000
            )
        res = await pool_engine.enqueue(
            s, users[3][0], game=CS2, metric=KD, difficulty="medium", entry_cents=1000
        )
        pool_id = res.pool.id
        room_bar = res.pool.room_bar
        # Backdate the window so it's due, and place a graded match inside it.
        start = datetime.now(UTC) - timedelta(hours=2)
        end = datetime.now(UTC) - timedelta(hours=1)
        await s.execute(
            update(SoloPool)
            .where(SoloPool.id == pool_id)
            .values(window_starts_at=start, window_ends_at=end)
        )
        await s.commit()
        mid_ms = int((start + timedelta(minutes=30)).timestamp() * 1000)

    # Two clear (KD above room_bar), two miss.
    games = {
        users[0][1]: [_game(mid_ms, room_bar + 0.5)],
        users[1][1]: [_game(mid_ms, room_bar + 0.5)],
        users[2][1]: [_game(mid_ms, 0.3)],
        users[3][1]: [_game(mid_ms, 0.3)],
    }
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    report = await settlement_worker.run_cycle(sm)
    assert report.pools_settled == 1
    async with sm() as s:
        pool = await s.get(SoloPool, pool_id)
        assert pool.state == "SETTLED"
        entries = list(
            await s.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool_id))
        )
        cleared = [e for e in entries if e.status == "CLEARED"]
        assert len(cleared) == 2 and all(e.payout_cents == 1800 for e in cleared)
        assert all(e.raw_payload_id is not None for e in entries)
        recon = await reconciliation_service.check(s, "solo_pool", pool_id)
        assert recon.ok
        assert (await reconciliation_service.check_all(s)).ok


async def test_pool_boundary_match_excluded_then_refunded(monkeypatch):
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())
    async with sm() as s:
        users = []
        for i, mu in enumerate([1.50, 1.50, 1.52, 1.48]):
            u, host = await _player(s, f"b{i}", mu=mu)
            users.append((u, host))
        for u, _ in users[:3]:
            await pool_engine.enqueue(
                s, u, game=CS2, metric=KD, difficulty="medium", entry_cents=1000
            )
        res = await pool_engine.enqueue(
            s, users[3][0], game=CS2, metric=KD, difficulty="medium", entry_cents=1000
        )
        pool_id = res.pool.id
        start = datetime.now(UTC) - timedelta(hours=2)
        end = datetime.now(UTC) - timedelta(hours=1)
        await s.execute(
            update(SoloPool)
            .where(SoloPool.id == pool_id)
            .values(window_starts_at=start, window_ends_at=end)
        )
        await s.commit()

    # Every match sits 1 ms BEFORE the window start → excluded → all unverifiable.
    before_ms = int(start.timestamp() * 1000) - 1
    games = {host: [_game(before_ms, 5.0)] for _, host in users}
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    await settlement_worker.run_cycle(sm)
    async with sm() as s:
        entries = list(
            await s.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool_id))
        )
        assert all(e.status == "REFUNDED" for e in entries)  # boundary match excluded


# --------------------------------------------------------------------------- #
# Tournaments.
# --------------------------------------------------------------------------- #


async def test_tournament_settles_and_pays_top_three(monkeypatch):
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())
    async with sm() as s:
        players = []
        for i in range(10):
            u, host = await _player(s, f"t{i}", mu=1.50 + i * 0.01)
            players.append((u, host))
        for u, _ in players[:-1]:
            await tournament_engine.enqueue(s, u, game=CS2, metric=KD, entry_cents=1000)
        res = await tournament_engine.enqueue(
            s, players[-1][0], game=CS2, metric=KD, entry_cents=1000
        )
        tid = res.tournament.id
        start = datetime.now(UTC) - timedelta(hours=2)
        end = datetime.now(UTC) - timedelta(hours=1)
        await s.execute(
            update(Tournament)
            .where(Tournament.id == tid)
            .values(window_starts_at=start, window_ends_at=end)
        )
        await s.commit()
        mid_ms = int((start + timedelta(minutes=30)).timestamp() * 1000)

    # Distinct descending KDs so ranking is unambiguous.
    games = {
        host: [_game(mid_ms, 2.0 - i * 0.1)] for i, (_, host) in enumerate(players)
    }
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    report = await settlement_worker.run_cycle(sm)
    assert report.tournaments_settled == 1
    async with sm() as s:
        tournament = await s.get(Tournament, tid)
        assert tournament.state == "SETTLED"
        paid = sorted(
            (
                e
                for e in await s.scalars(
                    select(TournamentEntry).where(TournamentEntry.tournament_id == tid)
                )
                if e.payout_cents > 0
            ),
            key=lambda e: e.rank,
        )
        assert [e.payout_cents for e in paid] == [4500, 2700, 1800]
        recon = await reconciliation_service.check(s, "tournament", tid)
        assert recon.ok
        assert (await reconciliation_service.check_all(s)).ok


async def test_tournament_standings_refresh_during_window(monkeypatch):
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())
    async with sm() as s:
        players = []
        for i in range(10):
            u, host = await _player(s, f"s{i}", mu=1.50 + i * 0.01)
            players.append((u, host))
        for u, _ in players[:-1]:
            await tournament_engine.enqueue(s, u, game=CS2, metric=KD, entry_cents=1000)
        res = await tournament_engine.enqueue(
            s, players[-1][0], game=CS2, metric=KD, entry_cents=1000
        )
        tid = res.tournament.id
        # Window still open (started an hour ago, ends in the future).
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        await s.execute(
            update(Tournament)
            .where(Tournament.id == tid)
            .values(window_starts_at=start, window_ends_at=end)
        )
        await s.commit()
        mid_ms = int((start + timedelta(minutes=10)).timestamp() * 1000)

    games = {
        host: [_game(mid_ms, 2.0 - i * 0.1)] for i, (_, host) in enumerate(players)
    }
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    report = await settlement_worker.run_cycle(sm)
    assert report.standings_refreshed == 1
    assert report.tournaments_settled == 0  # still in-window, not settled
    async with sm() as s:
        tournament = await s.get(Tournament, tid)
        rows = tournament.standings_cache["rows"]
        assert len(rows) == 10 and rows[0]["rank"] == 1
        assert rows[0]["score"] is not None
