"""Rolling tournaments: join-and-play, leaving, join close, and settlement.

Payout checks use the spec's examples (10% rake, 60/25/15): with ten players at
1000 the pot is 10000, rake 1000, and 9000 is split.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from moneymatch_api import clock
from moneymatch_api.constants import TOURNAMENT_WINDOW_SECONDS
from moneymatch_api.errors import APIError
from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import (
    reconciliation_service,
    tournament_engine,
    wallet_service,
)
from moneymatch_api.services.tournament_engine import TournamentGrade

from .factories import (
    create_linked_account,
    create_metric_model,
    create_user,
    create_wallet,
    cs2_profile,
)

pytestmark = pytest.mark.asyncio

CS2 = "cs2.steam"
KD = "cs2_kd_ratio"


async def t_player(session, name, *, mu=1.5, n=15, fund=10_000, model=True):
    user = await create_user(session, username=name)
    await create_linked_account(
        session, user, CS2, host_account_id=f"host_{name}", profile=cs2_profile(name)
    )
    if model:
        await create_metric_model(session, user, CS2, KD, mu=mu, sigma=0.3, n=n)
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user


async def join(session, user, *, entry=1000):
    return await tournament_engine.enqueue(
        session, user, game=CS2, metric=KD, entry_cents=entry
    )


async def _bal(session, user):
    w = await wallet_service.get_wallet(session, user.id)
    return w.available_cents, w.escrow_cents


async def _entries(session, tid):
    return list(
        await session.scalars(
            select(TournamentEntry)
            .where(TournamentEntry.tournament_id == tid)
            .order_by(TournamentEntry.enqueued_at)
        )
    )


async def _field(session, n, *, entry=1000):
    users = [await t_player(session, f"p{i}") for i in range(n)]
    result = None
    for u in users:
        result = await join(session, u, entry=entry)
    assert result is not None and result.tournament is not None
    return result.tournament, users


# --- joining ---------------------------------------------------------------- #


async def test_first_joiner_opens_a_tournament_and_is_escrowed(session):
    user = await t_player(session, "solo")
    result = await join(session, user)
    t = result.tournament
    assert result.status == "formed"
    assert t.state == "OPEN" and t.pot_cents == 1000
    # Alone: waiting for a second player, no clock yet.
    assert t.window_starts_at is None and t.window_ends_at is None
    assert t.join_closes_at is None
    assert await _bal(session, user) == (9000, 1000)


async def test_the_second_player_starts_the_clock(session):
    a, b = await t_player(session, "a"), await t_player(session, "b")
    t = (await join(session, a)).tournament
    assert tournament_engine.is_waiting(t)
    t = (await join(session, b)).tournament
    assert not tournament_engine.is_waiting(t) and t.state == "OPEN"
    assert t.window_ends_at - t.window_starts_at == timedelta(
        seconds=TOURNAMENT_WINDOW_SECONDS
    )
    # Others can keep joining until it ends (no separate join timer yet).
    assert t.join_closes_at == t.window_ends_at


async def test_a_third_and_fourth_player_join_the_running_tournament(session):
    players = [await t_player(session, n) for n in ("a", "b", "c", "d")]
    ids = {(await join(session, p)).tournament.id for p in players}
    assert len(ids) == 1
    (t_id,) = ids
    t = await session.get(Tournament, t_id)
    assert t.pot_cents == 4000 and len(await _entries(session, t_id)) == 4


async def test_second_joiner_lands_in_the_same_tournament(session):
    a, b = await t_player(session, "a"), await t_player(session, "b")
    ta = (await join(session, a)).tournament
    tb = (await join(session, b)).tournament
    assert ta.id == tb.id
    assert tb.pot_cents == 2000


async def test_a_different_entry_is_a_different_tournament(session):
    a, b = await t_player(session, "a"), await t_player(session, "b")
    ta = (await join(session, a, entry=1000)).tournament
    tb = (await join(session, b, entry=500)).tournament
    assert ta.id != tb.id


async def test_new_players_without_history_can_join(session):
    newbie = await t_player(session, "newbie", model=False)
    result = await join(session, newbie)
    (entry,) = await _entries(session, result.tournament.id)
    assert entry.baseline_snapshot["new_player"] is True


async def test_rejoining_returns_your_current_tournament(session):
    a = await t_player(session, "a")
    first = (await join(session, a)).tournament
    again = (await join(session, a)).tournament
    assert first.id == again.id
    assert await _bal(session, a) == (9000, 1000)  # not charged twice


async def test_a_full_tournament_locks_and_the_next_player_opens_another(session):
    t, _ = await _field(session, 10)
    assert t.state == "LOCKED"
    late = await t_player(session, "late")
    other = (await join(session, late)).tournament
    assert other.id != t.id and other.state == "OPEN"


# --- leaving ---------------------------------------------------------------- #


async def test_the_only_player_can_leave_for_a_full_refund(session):
    a = await t_player(session, "a")
    t = (await join(session, a)).tournament
    assert await tournament_engine.cancel(session, a) is True
    assert await _bal(session, a) == (10_000, 0)
    assert t.state == "CANCELED"
    assert (await reconciliation_service.check(session, "tournament", t.id)).ok


async def test_cannot_leave_once_someone_else_joined(session):
    a, b = await t_player(session, "a"), await t_player(session, "b")
    await join(session, a)
    await join(session, b)
    with pytest.raises(APIError) as exc:
        await tournament_engine.cancel(session, a)
    assert exc.value.code == "entry_final"


# --- joins closing ---------------------------------------------------------- #


async def test_a_solo_tournament_waits_however_long_it_takes(session):
    a = await t_player(session, "a")
    t = (await join(session, a)).tournament
    much_later = clock.now() + timedelta(days=3)
    await tournament_engine.close_joins(session, t, much_later)
    assert t.state == "OPEN" and tournament_engine.is_waiting(t)
    assert await _bal(session, a) == (9000, 1000)
    # And the next player still lands in it, starting the clock.
    b = await t_player(session, "b")
    assert (await join(session, b)).tournament.id == t.id


async def test_a_solo_tournament_refunds_at_settlement(session):
    a = await t_player(session, "a")
    t = (await join(session, a)).tournament
    (entry,) = await _entries(session, t.id)
    await tournament_engine.settle_tournament(
        session, t, {entry.id: TournamentGrade(values=[2.5])}
    )
    assert t.state == "CANCELED" and t.rake_cents == 0
    assert t.outcome_detail["reason"] == "not_enough_players"
    assert await _bal(session, a) == (10_000, 0)
    assert (await reconciliation_service.check(session, "tournament", t.id)).ok


async def test_a_solo_player_can_leave_even_after_joins_close(session):
    a = await t_player(session, "a")
    t = (await join(session, a)).tournament
    await tournament_engine.close_joins(session, t, t.join_closes_at)
    assert await tournament_engine.cancel(session, a) is True
    assert await _bal(session, a) == (10_000, 0)


async def test_join_close_with_two_players_locks(session):
    t, _ = await _field(session, 2)
    await tournament_engine.close_joins(session, t, t.join_closes_at)
    assert t.state == "LOCKED"


async def test_join_close_is_a_noop_before_the_deadline(session):
    t, _ = await _field(session, 2)
    await tournament_engine.close_joins(session, t, clock.now())
    assert t.state == "OPEN"


# --- settlement (spec payout examples) ------------------------------------- #


async def _settle(session, t, scores):
    """`scores` in join order; None = played nothing (forfeit)."""
    entries = await _entries(session, t.id)
    grades = {
        e.id: TournamentGrade(values=[] if s is None else [s])
        for e, s in zip(entries, scores, strict=True)
    }
    await tournament_engine.settle_tournament(session, t, grades)
    return await _entries(session, t.id)


def _payouts(entries):
    return [e.payout_cents for e in entries]


async def test_normal_split_is_60_25_15(session):
    t, _ = await _field(session, 10)
    entries = await _settle(session, t, [10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
    assert _payouts(entries)[:3] == [5400, 2250, 1350]
    assert sum(_payouts(entries)) == 9000
    assert t.rake_cents == 1000
    assert (await reconciliation_service.check(session, "tournament", t.id)).ok


async def test_tie_for_second_shares_second_and_third(session):
    t, _ = await _field(session, 10)
    entries = await _settle(session, t, [10, 9, 9, 7, 6, 5, 4, 3, 2, 1])
    assert _payouts(entries)[:3] == [5400, 1800, 1800]


async def test_two_tied_for_third_split_it_odd_unit_to_earlier_entry(session):
    t, _ = await _field(session, 10, entry=500)  # pot 5000 → 4500 distributable
    entries = await _settle(session, t, [10, 9, 8, 8, 6, 5, 4, 3, 2, 1])
    assert _payouts(entries)[:4] == [2700, 1125, 338, 337]


async def test_only_two_scorers_share_60_25_with_leftover_to_first(session):
    t, _ = await _field(session, 10, entry=500)
    entries = await _settle(session, t, [5, 4] + [None] * 8)
    # 4500 × 60/85 = 3176.47, × 25/85 = 1323.53 → 3176 + 1323 + 1 leftover.
    assert _payouts(entries)[:2] == [3177, 1323]
    assert t.rake_cents == 500  # exactly 10%, the leftover unit went to 1st


async def test_best_game_is_the_score(session):
    t, _ = await _field(session, 3)
    entries = await _entries(session, t.id)
    grades = {
        entries[0].id: TournamentGrade(values=[1.0, 3.0, 2.0]),
        entries[1].id: TournamentGrade(values=[2.5]),
        entries[2].id: TournamentGrade(values=[]),
    }
    await tournament_engine.settle_tournament(session, t, grades)
    entries = await _entries(session, t.id)
    assert entries[0].score == 3.0 and entries[0].rank == 1


async def test_two_player_tournament_is_winner_takes_the_prize(session):
    t, users = await _field(session, 2)
    entries = await _settle(session, t, [5, 3])
    assert _payouts(entries) == [1800, 0]
    assert await _bal(session, users[0]) == (10_800, 0)
    assert await _bal(session, users[1]) == (9000, 0)


async def test_three_players_pay_two_places(session):
    t, _ = await _field(session, 3)
    entries = await _settle(session, t, [5, 4, 3])
    # 2700 split 60/25 → 1905.88… / 794.11…, leftover unit to first.
    assert _payouts(entries) == [1906, 794, 0]


async def test_unverifiable_entrant_is_refunded_off_the_top(session):
    t, users = await _field(session, 3)
    entries = await _entries(session, t.id)
    grades = {
        entries[0].id: TournamentGrade(values=[5.0]),
        entries[1].id: TournamentGrade(values=[4.0]),
        entries[2].id: TournamentGrade(values=None),
    }
    await tournament_engine.settle_tournament(session, t, grades)
    entries = await _entries(session, t.id)
    assert entries[2].status == "REFUNDED" and entries[2].payout_cents == 1000
    assert [e.payout_cents for e in entries[:2]] == [1800, 0]
    assert (await reconciliation_service.check(session, "tournament", t.id)).ok


async def test_nobody_scored_voids_and_refunds(session):
    t, users = await _field(session, 3)
    await _settle(session, t, [None, None, None])
    assert t.state == "CANCELED" and t.rake_cents == 0
    assert t.outcome_detail["reason"] == "no_scores"
    for u in users:
        assert await _bal(session, u) == (10_000, 0)


async def test_settle_is_idempotent(session):
    t, _ = await _field(session, 2)
    await _settle(session, t, [5, 3])
    again = await tournament_engine.settle_tournament(session, t, {})
    assert again.state == "SETTLED"
    assert (await reconciliation_service.check(session, "tournament", t.id)).ok


async def test_one_live_tournament_per_player(session):
    a = await t_player(session, "a")
    first = (await join(session, a, entry=1000)).tournament
    # Picking another stat/entry while in one returns the one you are in.
    second = (await join(session, a, entry=500)).tournament
    assert second.id == first.id
    assert (
        await session.scalar(select(Tournament.id).where(Tournament.id != first.id))
    ) is None
