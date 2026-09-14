"""The self-driving demo tournament: it forms, injects updating stats, and settles
with money conserved (DB-backed).

Exercises `demo_tournament.start_live` + `tick` + the real settlement path, so a
browser tester can rely on the loop actually working.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.config import get_settings
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import (
    demo_tournament,
    telemetry_fetch,
    tournament_engine,
    wallet_service,
)
from tests.factories import create_user, create_wallet


@pytest.fixture
def simulate_on(monkeypatch):
    # The simulated adapter (which grades injected games) only wraps when this is on.
    monkeypatch.setattr(get_settings(), "demo_simulate_enabled", True)
    yield


async def _chess_link(session, user):
    session.add(
        LinkedAccount(
            user_id=user.id,
            game="chess.lichess",
            host_account_id=f"demo-{user.id}",
            host_username="demoplayer",
            profile_snapshot={"username": "demoplayer", "game": "chess.lichess"},
        )
    )
    await session.flush()


async def test_start_live_forms_field_holds_escrow_and_injects(session, simulate_on):
    user = await create_user(session)
    # Fund the demo user so escrow can be held.
    await create_wallet(session, user, available_cents=100_000)
    await _chess_link(session, user)

    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=4)
    assert t.state == "LOCKED"
    assert t.field_size == 5  # demo user + 4 bots
    assert t.prize_split == [60, 25, 15]

    entries = list(
        await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
        )
    )
    assert len(entries) == 5

    # The demo user's entry escrow is held.
    w = await wallet_service.get_wallet(session, user.id)
    assert w.escrow_cents == t.entry_cents

    # Window is ~10 minutes out.
    assert (t.window_ends_at - t.window_starts_at) >= timedelta(minutes=9)


async def test_tick_injects_more_games_when_due(session, simulate_on):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=100_000)
    await _chess_link(session, user)
    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=3)

    # Force the tick to be due by backdating last_tick.
    detail = dict(t.outcome_detail)
    detail["last_tick_ms"] = 0
    t.outcome_detail = detail
    await session.flush()

    advanced = await demo_tournament.tick(session)
    assert advanced == 1  # our one live tournament advanced


async def test_live_tournament_settles_top_three_with_money_conserved(
    session, simulate_on
):
    user = await create_user(session)
    await create_wallet(session, user, available_cents=100_000)
    await _chess_link(session, user)

    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=4)
    pot = t.pot_cents

    # Inject a few more rounds so everyone has a win count, then settle now.
    for _ in range(3):
        detail = dict(t.outcome_detail)
        detail["last_tick_ms"] = 0
        t.outcome_detail = detail
        await session.flush()
        await demo_tournament.tick(session)

    # Settle via the real worker path (grade → settle).
    entries_for_grade = list(
        await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
        )
    )
    grades = await telemetry_fetch.grade_tournament(session, t, entries_for_grade)
    await tournament_engine.settle_tournament(session, t, grades)
    await session.flush()

    settled = await session.get(Tournament, t.id)
    assert settled.state in ("SETTLED", "CANCELED")

    # Money conserved: every entry's stake is either paid out or refunded, and
    # payouts + rake == pot.
    entries = list(
        await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
        )
    )
    total_payout = sum(e.payout_cents for e in entries)
    assert total_payout + (settled.rake_cents or 0) == pot
    # At least the top place was paid (someone had a win count).
    assert any(e.payout_cents > 0 for e in entries)
