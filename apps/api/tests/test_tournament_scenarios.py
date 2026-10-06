"""Tournament scenarios end to end, with real accounts (no practice bots).

Each player is an ordinary signed-up user who joins through the HTTP API, so
matchmaking is the production path. A fake PUBG host stands in for the game API
and returns the games each player "played"; the ingester, scoring, settlement,
wallet and ledger are the real code. Every expected payout is worked out by
hand here (not by calling the engine's own split), so a wrong split fails.

Money at a $10 entry, 10% rake:
  2 players  pot $20 → $2 rake → $18 to 1 place                  (18.00)
  3 players  pot $30 → $3 rake → $27 to 2 places, 60/25           (19.06 / 7.94)
  4 players  pot $40 → $4 rake → $36 to 3 places, 60/25/15        (21.60 / 9.00 / 5.40)
A place pays only if someone scored there, and at least one participant is
always paid nothing (a 2-player tournament is winner-takes-the-prize).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from moneymatch_api import clock
from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import HistoryBatch, NormGame
from moneymatch_api.constants import (
    TOURNAMENT_FIELD_SIZE,
    TOURNAMENT_FINAL_POLL_TIMEOUT_SECONDS,
    TOURNAMENT_GRACE_SECONDS,
)
from moneymatch_api.db.session import get_sessionmaker
from moneymatch_api.models.tournament_log import TournamentResult
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import reconciliation_service, wallet_service
from moneymatch_api.services.hosts.errors import HostUnavailable
from moneymatch_api.workers import settlement_worker

from . import factories
from .conftest import auth_headers

pytestmark = pytest.mark.asyncio

PUBG = "pubg.steam"
KILLS = "pubg_kills"
ENTRY = 1000
START_BALANCE = 10_000
JOIN = {"game": PUBG, "metric": KILLS, "entry_preset_cents": ENTRY}


class FakePubg:
    """Per-account games; accounts in `down` fail every poll (unverifiable)."""

    id = PUBG
    brokered = False
    defer_bootstrap = False

    def __init__(self):
        self.games: dict[str, list[NormGame]] = {}
        self.down: set[str] = set()

    async def fetch_history(self, account_id, since_ms, *, known_ids, first_poll):
        if account_id in self.down:
            raise HostUnavailable("pubg", "down")
        return HistoryBatch(
            [g for g in self.games.get(account_id, []) if g.id not in known_ids],
            complete=True,
        )


@pytest.fixture
def pubg(monkeypatch):
    host = FakePubg()
    monkeypatch.setattr(registry, "host", lambda game_id: host)
    return host


class Player:
    def __init__(self, user, account):
        self.user, self.account = user, account
        self.headers = auth_headers(user.auth_id)


async def make_players(session, n: int) -> list[Player]:
    out = []
    for i in range(n):
        user = await factories.create_user(session, username=f"p{i + 1}")
        account = f"account.p{i + 1}_{user.id.hex[:6]}"
        await factories.create_linked_account(
            session, user, PUBG, host_account_id=account
        )
        await factories.create_wallet(session, user, available_cents=0)
        await wallet_service.demo_deposit(session, user.id, START_BALANCE, memo="fund")
        out.append(Player(user, account))
    await session.commit()
    return out


async def join(client, p: Player) -> dict:
    r = await client.post("/api/v1/tournaments/queue", json=JOIN, headers=p.headers)
    assert r.status_code == 200, r.text
    return r.json()["tournament"]


def pubg_game(gid: str, at, kills: float) -> NormGame:
    start = int(at.timestamp() * 1000)
    return NormGame(
        id=gid,
        speed="squad-fpp",
        rated=False,
        eligible=True,
        created_at_ms=start,
        moves=0,
        won=None,
        drawn=False,
        metrics={KILLS: float(kills)},
        ended_at_ms=start + 20 * 60_000,
    )


async def run_tournament(client, session, pubg, players, kills, *, down=()):
    """Everyone joins; each player's kills (a list per player, None = played
    nothing) are their games after the start; the worker settles it. Returns
    (tournament id, {player index: available balance})."""
    for p in players:
        t = await join(client, p)
    tid = t["id"]
    async with get_sessionmaker()() as s:
        row = await s.get(Tournament, tid)
        starts, ends = row.window_starts_at, row.window_ends_at
    for i, (p, ks) in enumerate(zip(players, kills, strict=True)):
        pubg.games[p.account] = [
            pubg_game(f"g{i}_{n}", starts + timedelta(minutes=5 + 25 * n), k)
            for n, k in enumerate(ks or [])
        ]
    for i in down:
        pubg.down.add(players[i].account)

    after = ends + timedelta(seconds=TOURNAMENT_GRACE_SECONDS[PUBG] + 60)
    if down:  # unverifiable entrants are given up on after the timeout
        after += timedelta(seconds=TOURNAMENT_FINAL_POLL_TIMEOUT_SECONDS)
    sm = get_sessionmaker()
    # PUBG's final fetch covers at most 2 accounts per worker cycle (its rate
    # limit), so a big field takes a few cycles to settle.
    for n in range(12):
        await settlement_worker.run_cycle(sm, now=after + timedelta(minutes=2 * n))
        if (await state_of(tid)).state in ("SETTLED", "CANCELED"):
            break

    balances = {}
    async with sm() as s:
        for i, p in enumerate(players):
            w = await wallet_service.get_wallet(s, p.user.id)
            assert w.escrow_cents == 0, "nothing may stay held after settlement"
            balances[i] = w.available_cents
        assert (await reconciliation_service.check(s, "tournament", tid)).ok
    return tid, balances


def won(prize: int) -> int:
    """Available balance after paying the entry and receiving `prize`."""
    return START_BALANCE - ENTRY + prize


async def state_of(tid) -> Tournament:
    async with get_sessionmaker()() as s:
        return await s.get(Tournament, tid)


# --- matchmaking --------------------------------------------------------------- #


async def test_one_player_waits_and_can_leave(client, session):
    (p,) = await make_players(session, 1)
    t = await join(client, p)
    assert t["state"] == "OPEN" and t["players"] == 1
    assert t["window_ends_at"] is None  # no clock while alone
    r = await client.delete("/api/v1/tournaments/queue", headers=p.headers)
    assert r.status_code == 200
    async with get_sessionmaker()() as s:
        w = await wallet_service.get_wallet(s, p.user.id)
        assert (w.available_cents, w.escrow_cents) == (START_BALANCE, 0)


async def test_two_three_four_players_all_land_in_one_tournament(client, session):
    players = await make_players(session, 4)
    seen = [await join(client, p) for p in players]
    assert len({t["id"] for t in seen}) == 1
    assert seen[0]["window_ends_at"] is None  # 1 player: waiting
    assert seen[1]["window_ends_at"] is not None  # 2nd player started it
    assert seen[1]["window_ends_at"] == seen[3]["window_ends_at"]  # clock fixed
    assert [t["players"] for t in seen] == [1, 2, 3, 4]
    # Once anyone else is in, an entry is final.
    r = await client.delete("/api/v1/tournaments/queue", headers=players[0].headers)
    assert r.status_code == 409


async def test_a_full_field_locks_and_the_next_player_opens_a_new_one(client, session):
    players = await make_players(session, TOURNAMENT_FIELD_SIZE + 1)
    first = [await join(client, p) for p in players[:TOURNAMENT_FIELD_SIZE]]
    assert first[-1]["state"] == "LOCKED"
    extra = await join(client, players[-1])
    assert extra["id"] != first[0]["id"] and extra["players"] == 1
    assert extra["window_ends_at"] is None


async def test_different_stakes_never_share_a_tournament(client, session):
    a, b = await make_players(session, 2)
    ta = await join(client, a)
    r = await client.post(
        "/api/v1/tournaments/queue",
        json={**JOIN, "entry_preset_cents": 500},
        headers=b.headers,
    )
    assert r.json()["tournament"]["id"] != ta["id"]


# --- payouts --------------------------------------------------------------------- #


async def test_two_players_winner_takes_the_prize(client, session, pubg):
    players = await make_players(session, 2)
    tid, bal = await run_tournament(client, session, pubg, players, [[3], [7]])
    assert (await state_of(tid)).state == "SETTLED"
    assert bal == {0: won(0), 1: won(1800)}
    assert (await state_of(tid)).rake_cents == 200


async def test_three_players_top_two_paid(client, session, pubg):
    players = await make_players(session, 3)
    tid, bal = await run_tournament(client, session, pubg, players, [[5], [9], [1]])
    assert bal == {0: won(794), 1: won(1906), 2: won(0)}
    assert (await state_of(tid)).rake_cents == 300


async def test_four_players_top_three_paid(client, session, pubg):
    players = await make_players(session, 4)
    tid, bal = await run_tournament(
        client, session, pubg, players, [[2], [8], [4], [6]]
    )
    assert bal == {0: won(0), 1: won(2160), 2: won(540), 3: won(900)}
    assert (await state_of(tid)).rake_cents == 400


async def test_best_of_your_first_three_games_counts(client, session, pubg):
    """PUBG kills: your best game among your first 3 after the start. A 4th
    game, however good, is past the cap."""
    players = await make_players(session, 2)
    _, bal = await run_tournament(
        client, session, pubg, players, [[1, 6, 2, 20], [5, 5, 5]]
    )
    assert bal == {0: won(1800), 1: won(0)}  # 6 beats 5; the 20 never counts


async def test_four_players_but_only_two_played(client, session, pubg):
    players = await make_players(session, 4)
    _, bal = await run_tournament(
        client, session, pubg, players, [[3], None, [5], None]
    )
    # Pot $40, $36 to 2 places at 60/25: 2541.18 / 1058.82 → remainder to 1st.
    assert bal == {0: won(1058), 1: won(0), 2: won(2542), 3: won(0)}


async def test_two_players_one_played_the_player_wins(client, session, pubg):
    players = await make_players(session, 2)
    _, bal = await run_tournament(client, session, pubg, players, [[0], None])
    # Even a 0-kill game is a score; not playing is not.
    assert bal == {0: won(1800), 1: won(0)}


async def test_nobody_played_everyone_is_refunded(client, session, pubg):
    players = await make_players(session, 3)
    tid, bal = await run_tournament(client, session, pubg, players, [None] * 3)
    t = await state_of(tid)
    assert t.state == "CANCELED" and t.outcome_detail["reason"] == "no_scores"
    assert bal == {0: START_BALANCE, 1: START_BALANCE, 2: START_BALANCE}
    assert t.rake_cents == 0


async def test_a_tie_for_first_splits_the_top_places(client, session, pubg):
    players = await make_players(session, 3)
    _, bal = await run_tournament(client, session, pubg, players, [[6], [6], [2]])
    # Two tied 1st share 1st + 2nd prize: (1906 + 794) / 2 = 1350 each.
    assert bal == {0: won(1350), 1: won(1350), 2: won(0)}


async def test_an_unverifiable_player_is_refunded_and_the_rest_settle(
    client, session, pubg
):
    """A player whose account can't be fetched gets their entry back; the
    others play for a pot of their own entries only."""
    players = await make_players(session, 3)
    _, bal = await run_tournament(
        client, session, pubg, players, [[4], [2], [9]], down=(2,)
    )
    # Pot of the two verifiable entries: $20 → $18 to 1 place.
    assert bal == {0: won(1800), 1: won(0), 2: START_BALANCE}


async def test_two_players_one_unverifiable_refunds_everyone(client, session, pubg):
    players = await make_players(session, 2)
    tid, bal = await run_tournament(
        client, session, pubg, players, [[4], [2]], down=(1,)
    )
    t = await state_of(tid)
    assert t.state == "CANCELED" and t.outcome_detail["reason"] == "not_enough_players"
    assert bal == {0: START_BALANCE, 1: START_BALANCE}


async def test_a_full_ten_player_field(client, session, pubg):
    players = await make_players(session, 10)
    kills = [[k] for k in (3, 9, 1, 7, 0, 5, 2, 8, 4, 6)]
    tid, bal = await run_tournament(client, session, pubg, players, kills)
    # Pot $100 → $10 rake → $90 at 60/25/15 = 5400 / 2250 / 1350.
    paid = {i: b - won(0) for i, b in bal.items() if b != won(0)}
    assert paid == {1: 5400, 7: 2250, 3: 1350}  # 9, 8, 7 kills
    assert (await state_of(tid)).rake_cents == 1000


async def test_a_game_finishing_after_the_end_does_not_count(client, session, pubg):
    players = await make_players(session, 2)
    for p in players:
        t = await join(client, p)
    async with get_sessionmaker()() as s:
        row = await s.get(Tournament, t["id"])
        starts, ends = row.window_starts_at, row.window_ends_at
    pubg.games[players[0].account] = [pubg_game("ok", starts + timedelta(minutes=5), 2)]
    # Starts 5 min before the end, ends 15 min after it.
    pubg.games[players[1].account] = [
        pubg_game("late", ends - timedelta(minutes=5), 20)
    ]
    sm = get_sessionmaker()
    after = ends + timedelta(seconds=TOURNAMENT_GRACE_SECONDS[PUBG] + 60)
    for n in range(4):
        await settlement_worker.run_cycle(sm, now=after + timedelta(minutes=2 * n))
    async with sm() as s:
        w0 = await wallet_service.get_wallet(s, players[0].user.id)
        w1 = await wallet_service.get_wallet(s, players[1].user.id)
    assert (w0.available_cents, w1.available_cents) == (won(1800), won(0))


async def test_every_settled_tournament_is_logged_per_player(client, session, pubg):
    players = await make_players(session, 4)
    tid, _ = await run_tournament(client, session, pubg, players, [[2], [8], [4], None])
    async with get_sessionmaker()() as s:
        rows = {
            r.username: r
            for r in await s.scalars(
                select(TournamentResult).where(TournamentResult.tournament_id == tid)
            )
        }
        entries = list(
            await s.scalars(
                select(TournamentEntry).where(TournamentEntry.tournament_id == tid)
            )
        )
    assert len(rows) == len(entries) == 4
    assert rows["p2"].outcome == "paid" and rows["p2"].rank == 1
    assert rows["p4"].outcome == "unpaid" and rows["p4"].score is None
    assert sum(r.payout_cents for r in rows.values()) == 3600


async def test_clock_is_set_from_the_second_join(client, session):
    a, b = await make_players(session, 2)
    await join(client, a)
    before = clock.now()
    t = await join(client, b)
    from datetime import datetime

    assert datetime.fromisoformat(t["window_starts_at"]) >= before - timedelta(
        seconds=1
    )
