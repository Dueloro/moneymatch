"""Background match ingestion + rolling tournaments end to end through the worker.

A fake host adapter stands in for the game API so each test controls exactly
which games a player "played"; everything else (the ingester, the stored
table, scoring, settlement, money) is the real code.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from moneymatch_api import clock
from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import HistoryBatch, NormGame
from moneymatch_api.config import get_settings
from moneymatch_api.constants import INGEST_RETRY_SECONDS
from moneymatch_api.db.session import get_sessionmaker
from moneymatch_api.models.game_match import GameMatch
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import (
    match_ingestion,
    reconciliation_service,
    tournament_engine,
    wallet_service,
)
from moneymatch_api.services.hosts import pubg
from moneymatch_api.services.hosts.errors import HostUnavailable
from moneymatch_api.workers import settlement_worker

from .factories import create_linked_account, create_user, create_wallet, cs2_profile

pytestmark = pytest.mark.asyncio

CS2 = "cs2.steam"
KD = "cs2_kd_ratio"


class FakeHost:
    """Per-account game lists; accounts in `failing` raise like an outage."""

    id = CS2
    brokered = False
    defer_bootstrap = False

    def __init__(self):
        self.games: dict[str, list[NormGame]] = {}
        self.failing: set[str] = set()
        # Accounts whose next poll returns a partial batch (still catching up).
        self.partial: set[str] = set()
        self.calls: list[str] = []

    async def fetch_history(self, account_id, since_ms, *, known_ids, first_poll):
        self.calls.append(account_id)
        if account_id in self.failing:
            raise HostUnavailable("fake", "down")
        return HistoryBatch(
            [g for g in self.games.get(account_id, []) if g.id not in known_ids],
            complete=account_id not in self.partial,
        )


@pytest.fixture
def fake_host(monkeypatch):
    host = FakeHost()
    monkeypatch.setattr(registry, "host", lambda game_id: host)
    return host


def game(gid: str, at, kd: float, *, minutes=30) -> NormGame:
    start_ms = int(at.timestamp() * 1000)
    return NormGame(
        id=gid,
        speed="premier",
        rated=True,
        created_at_ms=start_ms,
        moves=0,
        won=True,
        drawn=False,
        metrics={KD: kd},
        ended_at_ms=start_ms + minutes * 60_000,
    )


async def player(session, name, fund=10_000):
    user = await create_user(session, username=name)
    link = await create_linked_account(
        session, user, CS2, host_account_id=f"host_{name}", profile=cs2_profile(name)
    )
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user, link


# --- the ingester ------------------------------------------------------------- #


async def test_poll_stores_games_once(session, fake_host):
    _, link = await player(session, "a")
    now = clock.now()
    fake_host.games["host_a"] = [game("g1", now, 1.2), game("g2", now, 0.8)]

    assert await match_ingestion.poll_account(session, link, now=now) == 2
    assert await match_ingestion.poll_account(session, link, now=now) == 0  # idempotent
    rows = list(await session.scalars(select(GameMatch)))
    assert {r.host_match_id for r in rows} == {"g1", "g2"}
    assert link.ingest_polled_at == now and link.ingest_cursor_ms is not None


async def test_stored_games_cannot_be_edited(session, fake_host):
    _, link = await player(session, "a")
    fake_host.games["host_a"] = [game("g1", clock.now(), 1.2)]
    await match_ingestion.poll_account(session, link)
    await session.commit()
    with pytest.raises(DBAPIError):
        await session.execute(text("UPDATE game_matches SET result = 'win'"))
    await session.rollback()


async def test_run_cycle_polls_every_linked_account(fake_host, session):
    for name in ("a", "b"):
        await player(session, name)
    await session.commit()
    polled = await match_ingestion.run_cycle(get_sessionmaker())
    assert polled == 2 and set(fake_host.calls) == {"host_a", "host_b"}
    # Polled accounts are not due again until their interval passes.
    fake_host.calls.clear()
    assert await match_ingestion.run_cycle(get_sessionmaker()) == 0


async def test_a_failed_poll_is_retried_not_recorded_as_nothing_new(fake_host, session):
    _, link = await player(session, "a")
    await session.commit()
    fake_host.failing.add("host_a")
    await match_ingestion.run_cycle(get_sessionmaker())
    await session.refresh(link)
    assert link.ingest_attempted_at is not None and link.ingest_polled_at is None


async def test_tournament_players_are_polled_before_idle_accounts(fake_host, session):
    now = clock.now()
    idle_user, idle = await player(session, "idle")
    busy_user, busy = await player(session, "busy")
    # Both were polled a while ago: the idle one is not due for hours, the
    # tournament player is due on the fast cadence.
    for link in (idle, busy):
        link.ingest_attempted_at = link.ingest_polled_at = now - timedelta(minutes=5)
    rival_user, rival = await player(session, "rival")
    rival.ingest_attempted_at = rival.ingest_polled_at = now - timedelta(minutes=5)
    for u in (busy_user, rival_user):
        await tournament_engine.enqueue(
            session, u, game=CS2, metric=KD, entry_cents=1000
        )
    await session.commit()
    due = await match_ingestion.due_links(session, CS2, now, limit=5)
    assert busy.id in due and idle.id not in due


async def test_a_player_waiting_alone_is_not_polled_fast(fake_host, session):
    """Nothing can count before the clock starts, so no host calls on it."""
    now = clock.now()
    user, link = await player(session, "alone")
    link.ingest_attempted_at = link.ingest_polled_at = now - timedelta(minutes=5)
    await tournament_engine.enqueue(
        session, user, game=CS2, metric=KD, entry_cents=1000
    )
    await session.commit()
    assert link.id not in await match_ingestion.due_links(session, CS2, now, limit=5)


# --- PUBG: only new match ids are fetched --------------------------------------- #


@respx.mock
async def test_pubg_fetches_only_new_matches(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "pubg_api_key", "test-key")
    pubg.clear_match_cache()
    user = await create_user(session)
    link = LinkedAccount(
        user_id=user.id,
        game="pubg.steam",
        host_account_id="account.p",
        host_username="p",
    )
    session.add(link)
    await session.flush()

    shard = "https://api.pubg.com/shards/steam"

    def player_doc(ids):
        return {
            "data": {
                "id": "account.p",
                "attributes": {"name": "p"},
                "relationships": {
                    "matches": {"data": [{"type": "match", "id": i} for i in ids]}
                },
            }
        }

    def match_route(mid, day):
        return respx.get(f"{shard}/matches/{mid}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": mid,
                        "attributes": {
                            "gameMode": "squad-fpp",
                            "matchType": "official",
                            "isCustomMatch": False,
                            "createdAt": f"2026-09-{day:02d}T00:00:00Z",
                            "duration": 1800,
                        },
                    },
                    "included": [
                        {
                            "type": "participant",
                            "attributes": {
                                "stats": {
                                    "playerId": "account.p",
                                    "kills": 3,
                                    "headshotKills": 1,
                                    "damageDealt": 250.0,
                                    "winPlace": 4,
                                }
                            },
                        }
                    ],
                },
            )
        )

    first = respx.get(f"{shard}/players/account.p").mock(
        return_value=httpx.Response(200, json=player_doc(["m2", "m1"]))
    )
    r1, r2 = match_route("m1", 1), match_route("m2", 2)
    assert await match_ingestion.poll_account(session, link) == 2

    # Next poll: one new match on top. Only it is fetched.
    first.mock(return_value=httpx.Response(200, json=player_doc(["m3", "m2", "m1"])))
    r3 = match_route("m3", 3)
    assert await match_ingestion.poll_account(session, link) == 1
    assert (r1.call_count, r2.call_count, r3.call_count) == (1, 1, 1)

    row = await session.scalar(select(GameMatch).where(GameMatch.host_match_id == "m3"))
    assert row.ended_at is not None and row.metrics["pubg_kills"] == 3.0
    assert row.eligible is True


# --- rolling tournament through the worker -------------------------------------- #


async def test_rolling_tournament_settles_from_stored_games(fake_host, session):
    users = [await player(session, n) for n in ("a", "b", "c")]
    for user, _ in users:
        res = await tournament_engine.enqueue(
            session, user, game=CS2, metric=KD, entry_cents=1000
        )
    t = res.tournament
    await session.commit()

    t0 = t.window_starts_at
    fake_host.games = {
        "host_a": [game("a1", t0 + timedelta(minutes=5), 1.1)],
        "host_b": [
            game("b1", t0 + timedelta(minutes=5), 0.9),
            game("b2", t0 + timedelta(minutes=50), 2.4),  # best game counts
        ],
        # c plays one game that is still running at the end: it doesn't count.
        "host_c": [game("c1", t.window_ends_at - timedelta(minutes=5), 9.0)],
    }

    after = t.window_ends_at + timedelta(minutes=31)  # CS2 grace is 30 min
    report = await settlement_worker.run_cycle(get_sessionmaker(), now=after)
    assert report.tournaments_settled == 1

    sm = get_sessionmaker()
    async with sm() as s:
        tournament = await s.get(Tournament, t.id)
        assert tournament.state == "SETTLED"
        entries = {
            e.host_account_id: e
            for e in await s.scalars(
                select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
            )
        }
        assert entries["host_b"].rank == 1 and entries["host_b"].score == 2.4
        assert entries["host_a"].rank == 2
        assert entries["host_c"].score is None  # nothing counted
        # 3 players → 2 paid places: 2700 at 60/25 → 1906 / 794.
        assert entries["host_b"].payout_cents == 1906
        assert entries["host_a"].payout_cents == 794
        reasons = {
            g["host_match_id"]: g["reason"]
            for g in entries["host_c"].telemetry["games"]
        }
        assert reasons == {"c1": "ENDED_AFTER_CUTOFF"}
        assert (await reconciliation_service.check(s, "tournament", t.id)).ok


async def test_settlement_waits_for_the_final_poll_then_refunds_the_missing(
    fake_host, session
):
    users = [await player(session, n) for n in ("a", "b", "c")]
    for user, _ in users:
        res = await tournament_engine.enqueue(
            session, user, game=CS2, metric=KD, entry_cents=1000
        )
    t = res.tournament
    await session.commit()
    t0 = t.window_starts_at
    fake_host.games = {
        "host_a": [game("a1", t0 + timedelta(minutes=5), 1.1)],
        "host_b": [game("b1", t0 + timedelta(minutes=5), 0.9)],
    }
    fake_host.failing.add("host_c")  # c's account cannot be read

    after = t.window_ends_at + timedelta(minutes=31)
    report = await settlement_worker.run_cycle(get_sessionmaker(), now=after)
    assert report.tournaments_settled == 0  # waiting on c's final poll

    much_later = after + timedelta(hours=3)  # past the final-poll timeout
    report = await settlement_worker.run_cycle(get_sessionmaker(), now=much_later)
    assert report.tournaments_settled == 1
    async with get_sessionmaker()() as s:
        c = await s.scalar(
            select(TournamentEntry).where(
                TournamentEntry.tournament_id == t.id,
                TournamentEntry.host_account_id == "host_c",
            )
        )
        assert c.status == "REFUNDED" and c.payout_cents == 1000
        assert (await reconciliation_service.check(s, "tournament", t.id)).ok


async def test_a_solo_tournament_waits_and_never_settles(fake_host, session):
    """One player: no clock, so the worker never ends or settles it, and a game
    played while waiting does not count. Leaving refunds in full."""
    user, _ = await player(session, "lonely")
    t = (
        await tournament_engine.enqueue(
            session, user, game=CS2, metric=KD, entry_cents=1000
        )
    ).tournament
    await session.commit()
    fake_host.games = {"host_lonely": [game("x1", clock.now(), 1.4)]}
    sm = get_sessionmaker()

    await settlement_worker.run_cycle(sm, now=clock.now() + timedelta(days=2))
    async with sm() as s:
        waiting = await s.get(Tournament, t.id)
        assert waiting.state == "OPEN" and waiting.window_ends_at is None
        w = await wallet_service.get_wallet(s, user.id)
        assert (w.available_cents, w.escrow_cents) == (9_000, 1_000)
        me = await s.get(type(user), user.id)
        assert await tournament_engine.cancel(s, me) is True
        await s.commit()
        w = await wallet_service.get_wallet(s, user.id)
        assert (w.available_cents, w.escrow_cents) == (10_000, 0)


async def test_games_before_the_second_player_joined_do_not_count(fake_host, session):
    first, _ = await player(session, "first")
    second, _ = await player(session, "second")
    await tournament_engine.enqueue(
        session, first, game=CS2, metric=KD, entry_cents=1000
    )
    await session.commit()
    played_while_waiting = clock.now()
    t = (
        await tournament_engine.enqueue(
            session, second, game=CS2, metric=KD, entry_cents=1000
        )
    ).tournament
    await session.commit()
    fake_host.games = {
        "host_first": [
            game("early", played_while_waiting - timedelta(minutes=1), 9.0),
            game("late", t.window_starts_at + timedelta(minutes=5), 1.2),
        ],
        "host_second": [game("s1", t.window_starts_at + timedelta(minutes=5), 1.0)],
    }
    after = t.window_ends_at + timedelta(minutes=31)
    sm = get_sessionmaker()
    for i in range(3):
        await settlement_worker.run_cycle(sm, now=after + timedelta(minutes=i * 2))
    async with sm() as s:
        done = await s.get(Tournament, t.id)
        assert done.state == "SETTLED"
        entries = {
            e.user_id: e
            for e in await s.scalars(
                select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
            )
        }
        # The 9.0 game was played while waiting, so 1.2 is first's best.
        assert entries[first.id].score == 1.2 and entries[first.id].rank == 1
        assert (await reconciliation_service.check(s, "tournament", t.id)).ok


async def test_timings_can_be_shortened_for_testing(fake_host, session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tournament_window_seconds", 600)
    for name in ("quick", "quicker"):
        user, _ = await player(session, name)
        t = (
            await tournament_engine.enqueue(
                session, user, game=CS2, metric=KD, entry_cents=1000
            )
        ).tournament
    assert t.window_ends_at - t.window_starts_at == timedelta(seconds=600)
    assert t.join_closes_at == t.window_ends_at


async def test_live_standings_come_from_stored_games(fake_host, session):
    users = [await player(session, n) for n in ("a", "b")]
    for user, _ in users:
        res = await tournament_engine.enqueue(
            session, user, game=CS2, metric=KD, entry_cents=1000
        )
    t = res.tournament
    await session.commit()
    fake_host.games = {
        "host_a": [game("a1", t.window_starts_at + timedelta(minutes=5), 1.7)]
    }
    mid = t.window_starts_at + timedelta(hours=1)
    report = await settlement_worker.run_cycle(get_sessionmaker(), now=mid)
    assert report.tournaments_settled == 0 and report.standings_refreshed == 1
    async with get_sessionmaker()() as s:
        rows = (await s.get(Tournament, t.id)).standings_cache["rows"]
        top = next(r for r in rows if r["rank"] == 1)
        assert top["score"] == 1.7 and top["games"][0]["reason"] == "COUNTED"


# --- chess: a busy player is fully caught up in one poll ------------------------ #


async def test_chess_history_pages_until_caught_up(monkeypatch):
    from moneymatch_api.adapters.chess_lichess import ChessLichessAdapter
    from moneymatch_api.services.hosts import lichess

    def raw(i: int) -> dict:
        return {
            "id": f"g{i}",
            "status": "resign",
            "variant": "standard",
            "speed": "blitz",
            "rated": True,
            "createdAt": 1_000_000 + i,
            "lastMoveAt": 1_000_500 + i,
            "moves": "e4 e5 " * 12,
            "winner": "white",
            "players": {
                "white": {"user": {"id": "me"}, "rating": 1500},
                "black": {"user": {"id": f"opp{i}"}, "rating": 1480},
            },
        }

    calls: list[int] = []

    async def fake_games(account, since_ms, **kwargs):
        calls.append(since_ms)
        assert kwargs["oldest_first"] and kwargs["raise_errors"]
        start = 0 if len(calls) == 1 else 100
        count = 100 if len(calls) == 1 else 7
        return [raw(i) for i in range(start, start + count)]

    monkeypatch.setattr(lichess, "get_user_games", fake_games)
    batch = await ChessLichessAdapter().fetch_history(
        "me", 0, known_ids=set(), first_poll=True
    )
    games = batch.games
    assert batch.complete and len(games) == 107 and len(calls) == 2
    assert calls[1] == 1_000_000 + 99 + 1  # second page starts after the first
    assert games[0].detail["opponent_id"] == "opp0"


async def test_a_partial_backfill_is_not_counted_as_caught_up(fake_host, session):
    """A very active player's first poll can't fetch everything at once. Until
    it has, the account is not "polled" (so no tournament settles on it) and it
    is due again as soon as the retry pause is over."""
    _, link = await player(session, "busy")
    await session.commit()
    fake_host.partial.add("host_busy")
    now = clock.now()
    sm = get_sessionmaker()

    await match_ingestion.run_cycle(sm, now)
    await session.refresh(link)
    assert link.ingest_attempted_at == now and link.ingest_polled_at is None
    async with sm() as s:
        assert link.id in await match_ingestion.due_links(
            s, CS2, now + timedelta(seconds=INGEST_RETRY_SECONDS + 1), limit=5
        )

    fake_host.partial.clear()  # caught up on the next poll
    later = now + timedelta(seconds=INGEST_RETRY_SECONDS + 1)
    await match_ingestion.run_cycle(sm, later)
    await session.refresh(link)
    assert link.ingest_polled_at == later


async def test_chess_history_is_incomplete_when_every_page_is_full(monkeypatch):
    from moneymatch_api.adapters.chess_lichess import (
        _HISTORY_MAX_PAGES,
        _HISTORY_PAGE,
        ChessLichessAdapter,
    )
    from moneymatch_api.services.hosts import lichess

    page = 0

    async def full_pages(account, since_ms, **kwargs):
        nonlocal page
        page += 1
        base = page * 1000
        return [
            {
                "id": f"g{base + i}",
                "status": "resign",
                "variant": "standard",
                "speed": "blitz",
                "rated": True,
                "createdAt": base + i,
                "moves": "e4 e5",
                "winner": "white",
                "players": {
                    "white": {"user": {"id": "me"}},
                    "black": {"user": {"id": "x"}},
                },
            }
            for i in range(_HISTORY_PAGE)
        ]

    monkeypatch.setattr(lichess, "get_user_games", full_pages)
    batch = await ChessLichessAdapter().fetch_history(
        "me", 0, known_ids=set(), first_poll=True
    )
    assert page == _HISTORY_MAX_PAGES
    assert batch.complete is False


async def test_practice_bots_never_starve_real_accounts(fake_host, session):
    """Regression: 9 never-polled demo bots used to fill every batch (they were
    skipped after selection, so they stayed first in line forever)."""
    from moneymatch_api.services import test_opponents

    for i in range(9):
        bot = await create_user(session, username=f"bot{i}")
        await create_linked_account(
            session, bot, CS2, host_account_id=f"{test_opponents.TEST_AUTH_PREFIX}b{i}"
        )
    _, real = await player(session, "real")
    await session.commit()

    due = await match_ingestion.due_links(session, CS2, clock.now(), limit=2)
    assert due == [real.id]
    await match_ingestion.run_cycle(get_sessionmaker())
    assert fake_host.calls == ["host_real"]


async def test_a_failing_account_waits_before_its_next_try(fake_host, session):
    """Regression: a failed poll used to be retried every 15 s cycle, so one
    broken account spent the PUBG budget everyone else's polls need."""
    _, link = await player(session, "down")
    await session.commit()
    fake_host.failing.add("host_down")
    now = clock.now()
    sm = get_sessionmaker()

    await match_ingestion.run_cycle(sm, now)
    async with sm() as s:
        soon = now + timedelta(seconds=15)
        assert link.id not in await match_ingestion.due_links(s, CS2, soon, limit=5)
        rested = now + timedelta(seconds=INGEST_RETRY_SECONDS + 1)
        assert link.id in await match_ingestion.due_links(s, CS2, rested, limit=5)


async def test_demo_placeholder_handles_are_never_polled(fake_host, session):
    """The demo's made-up `<game>_<name>` links are unknown to every host; a
    poll could only fail and spend a call."""
    demo = await create_user(session, username="demo_like")
    await create_linked_account(session, demo, CS2, host_account_id=f"{CS2}_demo")
    _, real = await player(session, "real")
    await session.commit()

    due = await match_ingestion.due_links(session, CS2, clock.now(), limit=5)
    assert due == [real.id]
