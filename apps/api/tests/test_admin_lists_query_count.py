"""Admin lists run a fixed number of queries, however many rows they return."""

from __future__ import annotations

from sqlalchemy import event

from moneymatch_api.db.session import get_engine
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.routers.admin.users import search_users
from moneymatch_api.services import admin_contests_service

from .factories import create_linked_account, create_user, create_wallet

CHESS = "chess.lichess"


class _Counter:
    def __enter__(self):
        self.n = 0
        self._engine = get_engine().sync_engine
        event.listen(self._engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(self._engine, "before_cursor_execute", self._on)

    def _on(self, *args):
        self.n += 1


async def _users(session, start, count):
    out = []
    for i in range(start, start + count):
        user = await create_user(session, username=f"q_user_{i}")
        await create_wallet(session, user, available_cents=500)
        link = await create_linked_account(
            session, user, CHESS, host_account_id=f"q{i}"
        )
        out.append((user, link))
    await session.flush()
    return out


async def _match(session, a, b):
    match = Match(
        game=CHESS,
        market="win_h2h",
        speed="blitz",
        entry_cents=1000,
        rake_bps=1000,
        pot_cents=2000,
        prize_cents=1800,
        rake_cents=200,
        state="PENDING",
    )
    session.add(match)
    await session.flush()
    for user, link in (a, b):
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=user.id,
                linked_account_id=link.id,
                host_account_id=link.host_account_id,
            )
        )
    await session.flush()


async def test_user_list_query_count_does_not_grow(session):
    await _users(session, 0, 2)
    with _Counter() as few:
        first = await search_users(None, q="q_user", session=session)
    await _users(session, 2, 6)
    with _Counter() as many:
        second = await search_users(None, q="q_user", session=session)

    assert len(first.users) == 2 and len(second.users) == 8
    assert all(u.available_cents > 0 for u in second.users)
    assert many.n == few.n


async def test_contest_list_query_count_does_not_grow(session):
    players = await _users(session, 0, 2)
    await _match(session, *players)
    with _Counter() as few:
        first = await admin_contests_service.list_contests(session, ref_type="match")
    for _ in range(5):
        await _match(session, *players)
    with _Counter() as many:
        second = await admin_contests_service.list_contests(session, ref_type="match")

    assert len(first) == 1 and len(second) == 6
    assert all(c.participants == 2 for c in second)
    assert many.n == few.n
