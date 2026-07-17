"""Match lifecycle: confirm/escrow, activation (chess broker + coordinated),
decline/expiry refunds, and settle (win/push/cancel) with the money invariants.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.services import (
    match_lifecycle,
    reconciliation_service,
    wallet_service,
)
from moneymatch_api.services.hosts import lichess
from moneymatch_api.services.limits_service import StakeBlockedError
from moneymatch_api.services.match_lifecycle import (
    CANCEL,
    PUSH,
    WIN,
    LifecycleError,
    SettlementResult,
)

from .factories import create_wallet
from .test_matchmaking import CS2, chess_player, cs2_player, enq_chess, enq_cs2

pytestmark = pytest.mark.asyncio

ENTRY = 1000


async def _link(session, user):
    from moneymatch_api.models.linked_account import LinkedAccount

    return await session.scalar(
        select(LinkedAccount).where(LinkedAccount.user_id == user.id).limit(1)
    )


async def fund(session, user, amount_cents):
    """Give a user a real, promo-backed balance so global solvency stays checkable."""
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, amount_cents, memo="test fund")


async def paired_cs2(session, *, amount=10_000):
    """Two funded CS2 players paired into a PENDING match. Returns (match, a, b)."""
    a = await cs2_player(session, "alice", mu=1.0, sigma=0.3)
    b = await cs2_player(session, "bob", mu=1.0, sigma=0.3)
    await fund(session, a, amount)
    await fund(session, b, amount)
    await enq_cs2(session, a)
    match = (await enq_cs2(session, b)).match
    return match, a, b


async def _balances(session, user):
    w = await wallet_service.get_wallet(session, user.id)
    return w.available_cents, w.escrow_cents, w.lifetime_net_cents


# --- confirm / escrow ----------------------------------------------------- #


async def test_confirm_escrows_and_both_confirms_activate(session):
    match, a, b = await paired_cs2(session)
    await match_lifecycle.confirm(session, match, a)
    # One side confirmed → still PENDING, only that side escrowed.
    assert match.state == "PENDING"
    assert (await _balances(session, a))[:2] == (9000, 1000)
    assert (await _balances(session, b))[:2] == (10000, 0)

    await match_lifecycle.confirm(session, match, b)
    assert match.state == "ACTIVE"
    assert match.matched_at is not None  # server-stamped
    assert match.window_ends_at is not None
    assert (await _balances(session, b))[:2] == (9000, 1000)


async def test_double_confirm_is_idempotent(session):
    match, a, b = await paired_cs2(session)
    await match_lifecycle.confirm(session, match, a)
    await match_lifecycle.confirm(session, match, a)  # no second escrow
    assert (await _balances(session, a))[:2] == (9000, 1000)


async def test_confirm_insufficient_balance_fails_and_stays_pending(session):
    a = await cs2_player(session, "poor", mu=1.0, sigma=0.3)
    b = await cs2_player(session, "rich", mu=1.0, sigma=0.3)
    await fund(session, a, 500)  # < entry
    await fund(session, b, 10_000)
    await enq_cs2(session, a)
    match = (await enq_cs2(session, b)).match

    with pytest.raises(StakeBlockedError):
        await match_lifecycle.confirm(session, match, a)
    assert match.state == "PENDING"
    assert (await _balances(session, a))[:2] == (500, 0)  # nothing escrowed


async def test_chess_activation_brokers_and_sets_play_urls(session, monkeypatch):
    async def fake_challenge(clock_limit, clock_increment=0, *, users=None):
        assert users and len(users) == 2  # restricted to the two linked handles
        return {"game_id": "g123", "urls": {"white": "u/w", "black": "u/b"}}

    monkeypatch.setattr(lichess, "create_open_challenge", fake_challenge)

    a = await chess_player(session, "alice", rating=1500)
    b = await chess_player(session, "bob", rating=1510)
    await fund(session, a, 10_000)
    await fund(session, b, 10_000)
    await enq_chess(session, a)
    match = (await enq_chess(session, b)).match

    await match_lifecycle.confirm(session, match, a)
    await match_lifecycle.confirm(session, match, b)
    assert match.state == "ACTIVE" and match.host_game_id == "g123"
    seats = await match_lifecycle.players(session, match.id)
    assert {s.play_url for s in seats} == {"u/w", "u/b"}


async def test_chess_broker_failure_leaves_match_pending(session, monkeypatch):
    async def failed_challenge(clock_limit, clock_increment=0, *, users=None):
        return None  # host down / rejected

    monkeypatch.setattr(lichess, "create_open_challenge", failed_challenge)

    a = await chess_player(session, "alice")
    b = await chess_player(session, "bob", rating=1510)
    await fund(session, a, 10_000)
    await fund(session, b, 10_000)
    await enq_chess(session, a)
    match = (await enq_chess(session, b)).match

    await match_lifecycle.confirm(session, match, a)
    with pytest.raises(LifecycleError) as exc:
        await match_lifecycle.confirm(session, match, b)
    assert exc.value.code == "broker_failed"
    assert match.state == "PENDING"


# --- cancel / decline ----------------------------------------------------- #


async def test_decline_refunds_confirmer_no_rake(session):
    match, a, b = await paired_cs2(session)
    await match_lifecycle.confirm(session, match, a)  # only A escrowed
    await match_lifecycle.cancel_pending(session, match, reason="declined")
    assert match.state == "CANCELED"
    assert (await _balances(session, a))[:2] == (10000, 0)  # refunded in full
    recon = await reconciliation_service.check(session, "match", match.id)
    assert recon.ok and recon.totals["rake"] == 0


# --- settle --------------------------------------------------------------- #


async def _activate(session, match, a, b):
    await match_lifecycle.confirm(session, match, a)
    await match_lifecycle.confirm(session, match, b)
    assert match.state == "ACTIVE"


async def test_settle_win_pays_winner_and_books_rake(session):
    match, a, b = await paired_cs2(session)
    await _activate(session, match, a, b)

    await match_lifecycle.settle(
        session, match, SettlementResult(kind=WIN, winner_user_id=a.id)
    )
    assert match.state == "SETTLED" and match.winner_user_id == a.id
    # Winner: +$18 prize on a $10 stake → +$8 net; loser: −$10.
    a_av, a_es, a_life = await _balances(session, a)
    b_av, b_es, b_life = await _balances(session, b)
    assert (a_av, a_es, a_life) == (10800, 0, 800)
    assert (b_av, b_es, b_life) == (9000, 0, -1000)

    recon = await reconciliation_service.check(session, "match", match.id)
    assert recon.ok
    assert recon.totals["rake"] == 200  # $2 platform fee
    # sum(payouts) + rake == sum(entries): 1800 + 200 == 2000.
    assert recon.totals["distributed"] + recon.totals["rake"] == recon.totals["entries"]
    assert (await reconciliation_service.check_all(session)).ok


async def test_settle_friendly_win_refunds_both_records_winner(session):
    """A friendly (pair past the rake cap) grades a winner but refunds both
    entries with zero rake — the leaderboard-excluded, fun-only path (08-phase-5)."""
    from moneymatch_api.services import markets, matchmaking

    a = await cs2_player(session, "alice", mu=1.0, sigma=0.3)
    b = await cs2_player(session, "bob", mu=1.0, sigma=0.3)
    await fund(session, a, 10_000)
    await fund(session, b, 10_000)
    market = markets.get(CS2, "kd_ratio")
    match = await matchmaking.create_challenge_match(
        session,
        market=market,
        challenger=a,
        challenger_link=await _link(session, a),
        challengee=b,
        challengee_link=await _link(session, b),
        entry_cents=ENTRY,
        speed=None,
        friendly=True,
    )
    assert match.friendly is True and match.rake_bps == 0
    await _activate(session, match, a, b)

    await match_lifecycle.settle(
        session, match, SettlementResult(kind=WIN, winner_user_id=a.id)
    )
    assert match.state == "SETTLED" and match.winner_user_id == a.id  # recorded
    # Both fully refunded, zero net, zero rake.
    assert (await _balances(session, a)) == (10000, 0, 0)
    assert (await _balances(session, b)) == (10000, 0, 0)
    recon = await reconciliation_service.check(session, "match", match.id)
    assert recon.ok and recon.totals["rake"] == 0
    assert (await reconciliation_service.check_all(session)).ok


async def test_settle_push_refunds_both_no_rake(session):
    match, a, b = await paired_cs2(session)
    await _activate(session, match, a, b)
    await match_lifecycle.settle(session, match, SettlementResult(kind=PUSH))
    assert match.state == "PUSHED"
    assert (await _balances(session, a))[:2] == (10000, 0)
    assert (await _balances(session, b))[:2] == (10000, 0)
    recon = await reconciliation_service.check(session, "match", match.id)
    assert recon.ok and recon.totals["rake"] == 0


async def test_settle_cancel_refunds_both(session):
    match, a, b = await paired_cs2(session)
    await _activate(session, match, a, b)
    await match_lifecycle.settle(
        session,
        match,
        SettlementResult(kind=CANCEL, outcome_detail={"reason": "no_game"}),
    )
    assert match.state == "CANCELED"
    assert (await _balances(session, a))[:2] == (10000, 0)
    assert (await _balances(session, b))[:2] == (10000, 0)


async def test_settle_is_idempotent_on_terminal_match(session):
    match, a, b = await paired_cs2(session)
    await _activate(session, match, a, b)
    await match_lifecycle.settle(
        session, match, SettlementResult(kind=WIN, winner_user_id=a.id)
    )
    before = await _balances(session, a)
    # A second settle is a no-op (worker double-fire safe).
    await match_lifecycle.settle(
        session, match, SettlementResult(kind=WIN, winner_user_id=b.id)
    )
    assert await _balances(session, a) == before
    assert match.winner_user_id == a.id


async def test_settle_records_stat_lines_and_engine_version(session):
    match, a, b = await paired_cs2(session)
    await _activate(session, match, a, b)
    await match_lifecycle.settle(
        session,
        match,
        SettlementResult(
            kind=WIN,
            winner_user_id=a.id,
            stat_lines={a.id: {"cs2_kd_ratio": 1.4}, b.id: {"cs2_kd_ratio": 1.1}},
            engine_version="h2h-1",
        ),
    )
    seats = {s.user_id: s for s in await match_lifecycle.players(session, match.id)}
    assert seats[a.id].stat_line == {"cs2_kd_ratio": 1.4}
    assert match.engine_version == "h2h-1"
