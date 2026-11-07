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
    live_activity_service,
    pool_engine,
    reconciliation_service,
    tournament_engine,
    wallet_service,
)
from moneymatch_api.workers import settlement_worker

from .conftest import new_sessionmaker
from .factories import (
    chess_profile,
    create_linked_account,
    create_metric_model,
    create_user,
    create_wallet,
)

pytestmark = pytest.mark.asyncio

CHESS = "chess.lichess"
MOVES = "chess_moves"
WINS = "chess_wins"


class FakeAdapter:
    """Returns per-host games; used for both the sandbagging poll and grading."""

    id = CHESS

    def __init__(self, games_by_host=None):
        self.games_by_host = games_by_host or {}

    async def poll_eligible_games(self, host, since_ms, filters):
        return self.games_by_host.get(host, [])


def _game(created_ms: int, moves: float, *, won: bool = True) -> NormGame:
    """A rated game; `chess_moves` is only emitted for a win, as the adapter does."""
    return NormGame(
        id=f"m{created_ms}",
        speed="blitz",
        rated=True,
        created_at_ms=created_ms,
        moves=int(moves),
        won=won,
        drawn=False,
        metrics={MOVES: moves} if won else {},
    )


async def _player(session, name, *, mu=35.0, fund=10_000, host=None):
    host = host or f"host_{name}"
    user = await create_user(session, username=name)
    await create_linked_account(
        session, user, CHESS, host_account_id=host, profile=chess_profile(name)
    )
    await create_metric_model(session, user, CHESS, MOVES, mu=mu, sigma=8.0, n=15)
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user, host


async def _form_pool(s, prefix):
    """Four similar players forming a medium chess_moves room. Returns (users, pool)."""
    users = []
    for i, mu in enumerate([35.0, 35.0, 36.0, 34.0]):
        users.append(await _player(s, f"{prefix}{i}", mu=mu))
    res = None
    for u, _ in users:
        res = await pool_engine.enqueue(
            s, u, game=CHESS, metric=MOVES, difficulty="medium", entry_cents=1000
        )
    assert res is not None and res.pool is not None, "room did not form"
    return users, res.pool


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
        users, pool = await _form_pool(s, "p")
        pool_id = pool.id
        room_bar = pool.room_bar
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

    # Two clear (won in fewer moves than room_bar), two miss.
    games = {
        users[0][1]: [_game(mid_ms, room_bar - 5)],
        users[1][1]: [_game(mid_ms, room_bar - 5)],
        users[2][1]: [_game(mid_ms, room_bar + 20)],
        users[3][1]: [_game(mid_ms, room_bar + 20)],
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
        users, pool = await _form_pool(s, "b")
        pool_id = pool.id
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
    games = {host: [_game(before_ms, 10.0)] for _, host in users}
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    await settlement_worker.run_cycle(sm)
    async with sm() as s:
        entries = list(
            await s.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool_id))
        )
        assert all(e.status == "REFUNDED" for e in entries)  # boundary match excluded


async def test_live_snapshot_written_for_inflight_pool(monkeypatch):
    """An in-flight (not-yet-due) pool gets a per-member live snapshot cached,
    and `view_for` orients it to each viewer's first in-window match."""
    from moneymatch_api.models.live import LiveSnapshot
    from moneymatch_api.services import live_activity_service

    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())  # empty sandbag poll
    async with sm() as s:
        users, pool = await _form_pool(s, "L")
        pool_id = pool.id
        room_bar = pool.room_bar
        # The freshly-formed window is running (ends in the future) → not due,
        # so the worker only *refreshes live*, never settles it.
        start = pool.window_starts_at
        await s.commit()

    mid_ms = int((start + timedelta(minutes=30)).timestamp() * 1000)
    games = {
        users[0][1]: [_game(mid_ms, room_bar - 5)],  # clears
        users[2][1]: [_game(mid_ms, room_bar + 20)],  # misses
        # users[1] and users[3] have played nothing yet → "waiting".
    }
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    report = await settlement_worker.run_cycle(sm)
    assert report.pools_settled == 0  # in-flight, not settled
    assert report.live_refreshed >= 1

    async with sm() as s:
        row = await s.get(LiveSnapshot, ("pool", pool_id))
        assert row is not None
        members = row.data["members"]
        assert members[str(users[0][0].id)]["cleared"] is True
        assert members[str(users[2][0].id)]["cleared"] is False
        assert members[str(users[1][0].id)]["status"] == "waiting"

        # Oriented to the clearing viewer.
        view = live_activity_service.view_for("pool", row.data, users[0][0].id)
        assert view["status"] == "cleared" and view["cleared"] is True
        assert view["target"] == round(room_bar, 2)


async def test_pool_all_decided_predicate():
    """Every member verified (cleared|missed) ⇒ ready; any waiting/unavailable
    member ⇒ not ready; an empty snapshot ⇒ not ready. (Async only to satisfy the
    module-wide asyncio mark; the predicate itself is pure.)"""
    assert live_activity_service.pool_all_decided(
        {"members": {"a": {"status": "cleared"}, "b": {"status": "missed"}}}
    )
    assert not live_activity_service.pool_all_decided(
        {"members": {"a": {"status": "cleared"}, "b": {"status": "waiting"}}}
    )
    assert not live_activity_service.pool_all_decided(
        {"members": {"a": {"status": "unavailable"}}}
    )
    assert not live_activity_service.pool_all_decided({"members": {}})


async def test_pool_settles_early_when_all_members_decided(monkeypatch):
    """A still-in-window pool whose every entrant has a final result settles now
    (moves out of In play / Room formed) instead of waiting for the window end."""
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())
    async with sm() as s:
        users, pool = await _form_pool(s, "E")
        pool_id = pool.id
        room_bar = pool.room_bar
        start = pool.window_starts_at  # window is open — ends in the future
        await s.commit()

    mid_ms = int((start + timedelta(minutes=30)).timestamp() * 1000)
    # Every member has a decided in-window match → the outcome is already final.
    games = {
        users[0][1]: [_game(mid_ms, room_bar - 5)],  # clears
        users[1][1]: [_game(mid_ms, room_bar - 5)],  # clears
        users[2][1]: [_game(mid_ms, room_bar + 20)],  # misses
        users[3][1]: [_game(mid_ms, room_bar + 20)],  # misses
    }
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    # Cycle 1: the live refresh flags the pool ready but does not settle it yet
    # (settlement runs before the refresh within a cycle).
    r1 = await settlement_worker.run_cycle(sm)
    assert r1.pools_settled == 0
    async with sm() as s:
        pool = await s.get(SoloPool, pool_id)
        assert pool.state == "LOCKED"
        assert (pool.outcome_detail or {}).get("live_ready") is True

    # Cycle 2: the ready flag settles it before the window closes.
    r2 = await settlement_worker.run_cycle(sm)
    assert r2.pools_settled == 1
    async with sm() as s:
        pool = await s.get(SoloPool, pool_id)
        assert pool.state == "SETTLED"
        assert pool.window_ends_at > datetime.now(UTC)  # early, not at window end
        entries = list(
            await s.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool_id))
        )
        assert len([e for e in entries if e.status == "CLEARED"]) == 2
        assert (await reconciliation_service.check_all(s)).ok


async def test_pool_not_settled_early_while_a_member_is_still_playing(monkeypatch):
    """If any entrant has no result yet, the pool stays in play until its window
    ends — early settlement never strands a still-playing member's stake."""
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())
    async with sm() as s:
        users, pool = await _form_pool(s, "W")
        pool_id = pool.id
        room_bar = pool.room_bar
        start = pool.window_starts_at
        await s.commit()

    mid_ms = int((start + timedelta(minutes=30)).timestamp() * 1000)
    # Only two of four have played — the other two are still "waiting".
    games = {
        users[0][1]: [_game(mid_ms, room_bar - 5)],
        users[2][1]: [_game(mid_ms, room_bar + 20)],
    }
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter(games))

    r1 = await settlement_worker.run_cycle(sm)
    r2 = await settlement_worker.run_cycle(sm)
    assert r1.pools_settled == 0 and r2.pools_settled == 0
    async with sm() as s:
        pool = await s.get(SoloPool, pool_id)
        assert pool.state == "LOCKED"
        assert not (pool.outcome_detail or {}).get("live_ready")


# --------------------------------------------------------------------------- #
# Tournaments.
# --------------------------------------------------------------------------- #


async def test_tournament_settles_and_pays_top_three(monkeypatch):
    sm = new_sessionmaker()
    monkeypatch.setattr(registry, "get", lambda g: FakeAdapter())
    async with sm() as s:
        players = []
        for i in range(10):
            u, host = await _player(s, f"t{i}")
            players.append((u, host))
        for u, _ in players[:-1]:
            await tournament_engine.enqueue(
                s, u, game=CHESS, metric=WINS, entry_cents=1000
            )
        res = await tournament_engine.enqueue(
            s, players[-1][0], game=CHESS, metric=WINS, entry_cents=1000
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

    # Distinct descending win counts so ranking is unambiguous.
    games = {
        host: [_game(mid_ms + j, 30) for j in range(10 - i)]
        for i, (_, host) in enumerate(players)
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
            u, host = await _player(s, f"s{i}")
            players.append((u, host))
        for u, _ in players[:-1]:
            await tournament_engine.enqueue(
                s, u, game=CHESS, metric=WINS, entry_cents=1000
            )
        res = await tournament_engine.enqueue(
            s, players[-1][0], game=CHESS, metric=WINS, entry_cents=1000
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
        host: [_game(mid_ms + j, 30) for j in range(10 - i)]
        for i, (_, host) in enumerate(players)
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
