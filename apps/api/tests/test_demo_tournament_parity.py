"""The demo account plays a full tournament alone, and real signups never see it.

Joining as the demo fills the rest of the field with practice bots. The demo
scores from its real (relinked) account's games, exactly like anyone else; the
bots never play, finish last, and pay the demo out of their entries. Demo
tournaments and real ones never mix, in either direction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import HistoryBatch, NormGame
from moneymatch_api.config import get_settings
from moneymatch_api.constants import (
    DEMO_AUTH_ID,
    DEMO_USERNAME,
    TOURNAMENT_FIELD_SIZE,
    TOURNAMENT_GRACE_SECONDS,
)
from moneymatch_api.db.session import get_sessionmaker
from moneymatch_api.main import create_app
from moneymatch_api.models.tournament_log import TournamentMatchLog, TournamentResult
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.models.user import User
from moneymatch_api.services import (
    reconciliation_service,
    test_opponents,
    tournament_engine,
    wallet_service,
)
from moneymatch_api.workers import settlement_worker

from . import factories
from .conftest import auth_headers

pytestmark = pytest.mark.asyncio

PUBG = "pubg.steam"
KILLS = "pubg_kills"
ENTRY = 1000
JOIN = {"game": PUBG, "metric": KILLS, "entry_preset_cents": ENTRY}
DEMO_HEADERS = auth_headers(DEMO_AUTH_ID, email="demo@dueloro.com")


class FakePubg:
    """Stands in for the PUBG API: per-account game lists."""

    id = PUBG
    brokered = False
    defer_bootstrap = False

    def __init__(self):
        self.games: dict[str, list[NormGame]] = {}
        self.calls: list[str] = []

    async def fetch_history(self, account_id, since_ms, *, known_ids, first_poll):
        self.calls.append(account_id)
        return HistoryBatch(
            [g for g in self.games.get(account_id, []) if g.id not in known_ids],
            complete=True,
        )


@pytest.fixture
def fake_pubg(monkeypatch):
    host = FakePubg()
    monkeypatch.setattr(registry, "host", lambda game_id: host)
    return host


@pytest_asyncio.fixture
async def demo_client() -> AsyncIterator[AsyncClient]:
    settings = get_settings().model_copy(update={"demo_login_enabled": True})
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as c:
        yield c


async def _demo(session, host_account_id="account.demo_real"):
    user = User(
        auth_id=DEMO_AUTH_ID,
        username=DEMO_USERNAME,
        email="demo@dueloro.com",
        residence_state="MA",
        dob_attested_18plus=True,
    )
    session.add(user)
    await session.flush()
    link = await factories.create_linked_account(
        session, user, PUBG, host_account_id=host_account_id
    )
    await factories.create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, 10_000, memo="fund")
    await session.commit()
    return user, link


async def _real(session, name):
    user = await factories.create_user(session, username=name)
    link = await factories.create_linked_account(
        session, user, PUBG, host_account_id=f"account.{name}"
    )
    await factories.create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, 10_000, memo="fund")
    await session.commit()
    return user, link


def _pubg_game(gid, at, kills) -> NormGame:
    start_ms = int(at.timestamp() * 1000)
    return NormGame(
        id=gid,
        speed="squad-fpp",
        rated=False,
        eligible=True,
        created_at_ms=start_ms,
        moves=0,
        won=None,
        drawn=False,
        metrics={KILLS: float(kills)},
        ended_at_ms=start_ms + 25 * 60_000,
    )


async def test_demo_join_fills_the_field_with_bots(demo_client, session):
    await _demo(session)

    r = await demo_client.post(
        "/api/v1/tournaments/queue", json=JOIN, headers=DEMO_HEADERS
    )
    assert r.status_code == 200, r.text
    t = r.json()["tournament"]
    assert t["players"] == TOURNAMENT_FIELD_SIZE
    assert t["state"] == "LOCKED"  # full, so nobody else can join it


async def test_demo_on_its_placeholder_handle_is_told_to_relink(demo_client, session):
    await _demo(session, host_account_id=f"{PUBG}_{DEMO_USERNAME}")

    r = await demo_client.post(
        "/api/v1/tournaments/queue", json=JOIN, headers=DEMO_HEADERS
    )
    assert r.status_code == 409
    assert "demo_needs_real_account" in r.text


async def test_real_players_never_join_a_demo_tournament(session):
    """Even a demo tournament with room left (bots failed to fill) stays apart."""
    demo, _ = await _demo(session)
    real, _ = await _real(session, "realone")

    demo_t = (
        await tournament_engine.enqueue(
            session, demo, game=PUBG, metric=KILLS, entry_cents=ENTRY
        )
    ).tournament
    real_t = (
        await tournament_engine.enqueue(
            session, real, game=PUBG, metric=KILLS, entry_cents=ENTRY
        )
    ).tournament
    assert demo_t.state == "OPEN" and real_t.id != demo_t.id


async def test_the_demo_never_joins_a_real_tournament(demo_client, session):
    real, _ = await _real(session, "realtwo")
    real_t = (
        await tournament_engine.enqueue(
            session, real, game=PUBG, metric=KILLS, entry_cents=ENTRY
        )
    ).tournament
    await session.commit()
    await _demo(session)

    r = await demo_client.post(
        "/api/v1/tournaments/queue", json=JOIN, headers=DEMO_HEADERS
    )
    assert r.status_code == 200, r.text
    assert r.json()["tournament"]["id"] != str(real_t.id)
    players = await session.scalar(
        select(func.count())
        .select_from(TournamentEntry)
        .where(TournamentEntry.tournament_id == real_t.id)
    )
    assert players == 1  # no bots were dropped into the real player's field


async def test_demo_plays_a_real_game_and_is_paid_out(demo_client, session, fake_pubg):
    """The whole demo loop through the worker: join, bots fill, the demo's real
    account plays one PUBG match, the tournament ends, the demo takes the pot."""
    demo, link = await _demo(session)
    r = await demo_client.post(
        "/api/v1/tournaments/queue", json=JOIN, headers=DEMO_HEADERS
    )
    assert r.status_code == 200, r.text
    tid = r.json()["tournament"]["id"]

    async with get_sessionmaker()() as s:
        t = await s.get(Tournament, tid)
        pot = t.pot_cents
        starts, ends = t.window_starts_at, t.window_ends_at
    assert pot == ENTRY * TOURNAMENT_FIELD_SIZE
    fake_pubg.games[link.host_account_id] = [
        _pubg_game("m1", starts + timedelta(minutes=10), kills=4)
    ]

    after = ends + timedelta(seconds=TOURNAMENT_GRACE_SECONDS[PUBG] + 60)
    sm = get_sessionmaker()
    for i in range(3):  # final poll, then settle
        await settlement_worker.run_cycle(sm, now=after + timedelta(minutes=i * 2))

    async with sm() as s:
        t = await s.get(Tournament, tid)
        assert t.state == "SETTLED"
        wallet = await wallet_service.get_wallet(s, demo.id)
        # The demo paid one entry and won the pot minus the rake.
        assert wallet.available_cents > 10_000
        assert wallet.escrow_cents == 0
        assert (await reconciliation_service.check(s, "tournament", t.id)).ok
    # Bots were never looked up at the host.
    assert all(not test_opponents.is_practice_opponent(a) for a in fake_pubg.calls)


async def _settled_demo_tournament(demo_client, session, fake_pubg):
    """Join as the demo, play one 4-kill game, run the worker past the end."""
    demo, link = await _demo(session)
    r = await demo_client.post(
        "/api/v1/tournaments/queue", json=JOIN, headers=DEMO_HEADERS
    )
    assert r.status_code == 200, r.text
    tid = r.json()["tournament"]["id"]
    async with get_sessionmaker()() as s:
        t = await s.get(Tournament, tid)
        starts, ends = t.window_starts_at, t.window_ends_at
    fake_pubg.games[link.host_account_id] = [
        _pubg_game("early", starts - timedelta(minutes=30), kills=9),
        _pubg_game("m1", starts + timedelta(minutes=10), kills=4),
    ]
    after = ends + timedelta(seconds=TOURNAMENT_GRACE_SECONDS[PUBG] + 60)
    for i in range(3):
        await settlement_worker.run_cycle(
            get_sessionmaker(), now=after + timedelta(minutes=i * 2)
        )
    return demo, link, tid


async def test_settlement_writes_a_permanent_log(demo_client, session, fake_pubg):
    """Every entrant's result and every fetched match, with its verdict and
    timestamps, is kept once the tournament is paid out."""
    demo, link, tid = await _settled_demo_tournament(demo_client, session, fake_pubg)

    async with get_sessionmaker()() as s:
        results = list(
            await s.scalars(
                select(TournamentResult).where(TournamentResult.tournament_id == tid)
            )
        )
        assert len(results) == TOURNAMENT_FIELD_SIZE
        mine = next(r for r in results if r.user_id == demo.id)
        assert mine.outcome == "paid" and mine.rank == 1 and mine.score == 4.0
        assert mine.payout_cents > 0 and mine.username == DEMO_USERNAME
        assert sum(r.outcome == "forfeit" for r in results) == TOURNAMENT_FIELD_SIZE - 1

        log = {
            m.host_match_id: m
            for m in await s.scalars(
                select(TournamentMatchLog).where(
                    TournamentMatchLog.tournament_id == tid
                )
            )
        }
        assert set(log) == {"early", "m1"}
        assert log["m1"].counted and log["m1"].value == 4.0
        assert log["m1"].metrics == {KILLS: 4.0}
        assert log["m1"].fetched_at is not None and log["m1"].game_match_id
        assert not log["early"].counted
        assert log["early"].reason == "STARTED_BEFORE_START"


async def test_the_log_cannot_be_edited(demo_client, session, fake_pubg):
    _, _, tid = await _settled_demo_tournament(demo_client, session, fake_pubg)
    async with get_sessionmaker()() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "UPDATE tournament_match_log SET value = 99 "
                    "WHERE tournament_id = :t"
                ),
                {"t": tid},
            )
        await s.rollback()
        with pytest.raises(DBAPIError):
            await s.execute(
                text("DELETE FROM tournament_results WHERE tournament_id = :t"),
                {"t": tid},
            )


async def test_admins_can_read_the_log(demo_client, session, fake_pubg):
    demo, _, tid = await _settled_demo_tournament(demo_client, session, fake_pubg)
    await demo_client.get("/api/v1/me", headers=auth_headers("auth_admin"))
    async with get_sessionmaker()() as s:
        admin = await s.scalar(select(User).where(User.auth_id == "auth_admin"))
        admin.role = "admin"
        await s.commit()

    r = await demo_client.get(
        f"/api/v1/admin/tournaments/{tid}/log", headers=auth_headers("auth_admin")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entrants"]) == TOURNAMENT_FIELD_SIZE
    top = body["entrants"][0]
    assert top["username"] == DEMO_USERNAME and top["outcome"] == "paid"
    counted = [m for m in top["matches"] if m["counted"]]
    assert [m["host_match_id"] for m in counted] == ["m1"]
    assert counted[0]["reason_text"] == "Counted"

    # Players cannot read it.
    r = await demo_client.get(
        f"/api/v1/admin/tournaments/{tid}/log", headers=DEMO_HEADERS
    )
    assert r.status_code == 403


async def test_an_admin_void_is_logged_too(demo_client, session, fake_pubg):
    demo, link = await _demo(session)
    r = await demo_client.post(
        "/api/v1/tournaments/queue", json=JOIN, headers=DEMO_HEADERS
    )
    tid = r.json()["tournament"]["id"]
    await demo_client.get("/api/v1/me", headers=auth_headers("auth_admin"))
    async with get_sessionmaker()() as s:
        admin = await s.scalar(select(User).where(User.auth_id == "auth_admin"))
        admin.role = "admin"
        await s.commit()

    r = await demo_client.post(
        f"/api/v1/admin/tournaments/{tid}/void",
        json={"reason": "player reported a disconnect " * 4},
        headers=auth_headers("auth_admin"),
    )
    assert r.status_code == 200, r.text
    async with get_sessionmaker()() as s:
        results = list(
            await s.scalars(
                select(TournamentResult).where(TournamentResult.tournament_id == tid)
            )
        )
        assert len(results) == TOURNAMENT_FIELD_SIZE
        mine = next(x for x in results if x.user_id == demo.id)
        assert mine.outcome == "refunded"
        assert mine.tournament_outcome.startswith("admin: player reported")
