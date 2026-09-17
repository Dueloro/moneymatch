"""The self-driving simulation tournament: forms, standings MOVE and are DISTINCT,
forced ticks fast-forward, and it settles paying distinct 60/25/15 with money
conserved (DB-backed). Works for any signed-in user (no game link required).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.config import get_settings
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import demo_tournament, wallet_service
from tests.factories import create_user, create_wallet


@pytest.fixture
def simulate_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_simulate_enabled", True)
    yield


async def _player(session):
    # A plain user with NO chess link and a funded wallet — a real signup.
    user = await create_user(session)
    await create_wallet(session, user, available_cents=100_000)
    return user


async def test_start_creates_sim_link_and_opening_standings(session, simulate_on):
    user = await _player(session)
    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=4)
    assert t.field_size == 5
    assert t.prize_split == [60, 25, 15]

    from moneymatch_api.models.linked_account import LinkedAccount

    link = await session.scalar(
        select(LinkedAccount).where(LinkedAccount.user_id == user.id)
    )
    assert link is not None and link.host_account_id == f"sim:{user.id}"

    w = await wallet_service.get_wallet(session, user.id)
    assert w.escrow_cents == t.entry_cents
    rows = (t.standings_cache or {}).get("rows")
    assert rows and len(rows) == 5
    assert all("rank" in r and "score" in r for r in rows)


async def test_forced_tick_always_advances_and_moves_standings(session, simulate_on):
    user = await _player(session)
    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=4)
    before = {r["user_id"]: r["score"] for r in t.standings_cache["rows"]}

    assert await demo_tournament.tick(session, force=True) == 1
    assert await demo_tournament.tick(session, force=True) == 1

    t2 = await session.get(Tournament, t.id)
    after = {r["user_id"]: r["score"] for r in t2.standings_cache["rows"]}
    assert all(after[uid] > before[uid] for uid in before)


async def test_standings_are_distinct_ranks(session, simulate_on):
    user = await _player(session)
    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=5)
    for _ in range(3):
        await demo_tournament.tick(session, force=True)
    t2 = await session.get(Tournament, t.id)
    ranks = sorted(r["rank"] for r in t2.standings_cache["rows"])
    assert ranks == [1, 2, 3, 4, 5, 6]


async def test_settles_distinct_60_25_15_money_conserved(session, simulate_on):
    user = await _player(session)
    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=4)
    pot = t.pot_cents
    for _ in range(4):
        await demo_tournament.tick(session, force=True)

    settled = await demo_tournament.settle(session, t)
    assert settled.state == "SETTLED"

    entries = list(
        await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
        )
    )
    payouts = sorted((e.payout_cents for e in entries), reverse=True)
    positive = [p for p in payouts if p > 0]
    assert len(positive) == 3
    assert positive[0] > positive[1] > positive[2]
    assert sum(e.payout_cents for e in entries) + settled.rake_cents == pot
    # The exact split the engine computes (rake floored off the pot, then the
    # remainder split 60/25/15, remainder-cents back to rake).
    from moneymatch_api.services import money_math

    expected = money_math.split_weighted(pot, (60, 25, 15), settled.rake_bps)
    assert positive == list(expected.payouts_cents)
    assert settled.rake_cents == expected.rake_cents


async def test_worker_routes_live_tournament_to_own_settle(session, simulate_on):
    user = await _player(session)
    t = await demo_tournament.start_live(session, user, minutes=10, num_bots=4)
    assert demo_tournament.is_live_tournament(t) is True

    t.window_ends_at = t.window_starts_at + timedelta(minutes=10)
    for _ in range(2):
        await demo_tournament.tick(session, force=True)
    settled = await demo_tournament.settle(session, t)
    assert settled.state == "SETTLED"


async def test_matches_the_joined_game_and_metric(session, simulate_on):
    """A CS2 tournament fills with CS2 bots and ranks on the joined CS2 metric —
    the self-driving tournament follows the game the player joined, not chess."""
    user = await _player(session)
    t = await demo_tournament.start_live(
        session, user, game="cs2.steam", metric="cs2_kills", num_bots=4
    )
    assert t.game == "cs2.steam"
    assert t.ranking_metric == "cs2_kills"

    from moneymatch_api.models.linked_account import LinkedAccount

    link = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id, LinkedAccount.game == "cs2.steam"
        )
    )
    assert link is not None  # a synthetic CS2 link was created

    for _ in range(3):
        await demo_tournament.tick(session, force=True)
    t2 = await session.get(Tournament, t.id)
    ranks = sorted(r["rank"] for r in t2.standings_cache["rows"])
    assert ranks == [1, 2, 3, 4, 5]  # 5 distinct places, board moved


async def test_chess_is_limited_to_one_mode(session, simulate_on):
    """Chess collapses to a single mode: whatever chess metric is joined, it runs
    on per-game move count (blitz), so one chess tournament shape settles cleanly."""
    user = await _player(session)
    t = await demo_tournament.start_live(
        session, user, game="chess.lichess", metric="chess_wins"
    )
    assert t.ranking_metric == "chess_moves"  # not the joined aggregate metric
