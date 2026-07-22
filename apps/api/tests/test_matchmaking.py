"""DB-backed matchmaking: compatibility, forecast eligibility, widening, selection,
the anti-collusion `can_pair` seam, race-safety, and frozen baselines.

Ports `poc-reference/tests/test_matchmaking.py` against the Postgres service and
adds the duel-forecast cases the PoC never had.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from moneymatch_api.models.play import Match, QueueTicket
from moneymatch_api.services import matchmaking
from moneymatch_api.services.matchmaking import MatchmakingError

from .conftest import new_sessionmaker
from .factories import (
    chess_profile,
    create_linked_account,
    create_metric_model,
    create_user,
    cs2_profile,
)

pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
CHESS = "chess.lichess"
KD = "cs2_kd_ratio"


async def cs2_player(session, name, *, mu=1.0, sigma=0.5, n=15, rating=1500, host=None):
    user = await create_user(session, username=name)
    await create_linked_account(
        session,
        user,
        CS2,
        host_account_id=host,
        profile=cs2_profile(name, rating=rating),
    )
    # Seed all CS2 stat metrics so any CS2 market is queueable in tests.
    for metric in ("cs2_kd_ratio", "cs2_adr", "cs2_headshot_pct"):
        await create_metric_model(session, user, CS2, metric, mu=mu, sigma=sigma, n=n)
    return user


async def chess_player(session, name, *, rating=1500, speed="blitz", host=None):
    user = await create_user(session, username=name)
    await create_linked_account(
        session,
        user,
        CHESS,
        host_account_id=host,
        profile=chess_profile(name, rating=rating, speed=speed),
    )
    return user


async def enq_cs2(session, user, *, market="kd_ratio", entry=1000):
    return await matchmaking.enqueue(
        session, user, game=CS2, market_key=market, entry_cents=entry
    )


async def enq_chess(session, user, *, entry=1000, speed="blitz"):
    return await matchmaking.enqueue(
        session, user, game=CHESS, market_key="win_h2h", entry_cents=entry, speed=speed
    )


# --- ported PoC behaviour ------------------------------------------------- #


async def test_first_searches_second_matches(session):
    alice = await cs2_player(session, "alice")
    bob = await cs2_player(session, "bob")
    assert (await enq_cs2(session, alice)).status == "searching"
    r = await enq_cs2(session, bob)
    assert r.status == "matched"
    assert r.match.state == "PENDING" and r.match.entry_cents == 1000
    # Alice now polls to matched.
    assert (await matchmaking.poll_status(session, alice)).status == "matched"


async def test_incompatible_entry_does_not_pair(session):
    alice = await cs2_player(session, "alice")
    bob = await cs2_player(session, "bob")
    await enq_cs2(session, alice, entry=1000)
    assert (await enq_cs2(session, bob, entry=2500)).status == "searching"


async def test_different_market_does_not_pair(session):
    alice = await cs2_player(session, "alice")
    bob = await cs2_player(session, "bob")
    await enq_cs2(session, alice, market="kd_ratio")
    assert (await enq_cs2(session, bob, market="adr")).status == "searching"


async def test_chess_is_brokered_with_colors(session):
    alice = await chess_player(session, "alice", rating=1500)
    bob = await chess_player(session, "bob", rating=1520)
    await enq_chess(session, alice)
    m = (await enq_chess(session, bob)).match
    assert m.brokered is True
    players = list(
        await session.scalars(
            select(matchmaking.MatchPlayer).where(
                matchmaking.MatchPlayer.match_id == m.id
            )
        )
    )
    assert {p.color for p in players} == {"white", "black"}


async def test_cs2_is_coordinated_no_colors(session):
    alice = await cs2_player(session, "alice")
    bob = await cs2_player(session, "bob")
    await enq_cs2(session, alice)
    m = (await enq_cs2(session, bob)).match
    assert m.brokered is False
    players = list(
        await session.scalars(
            select(matchmaking.MatchPlayer).where(
                matchmaking.MatchPlayer.match_id == m.id
            )
        )
    )
    assert all(p.color is None for p in players)


async def test_chess_far_rating_does_not_pair_fresh(session):
    alice = await chess_player(session, "alice", rating=1200)
    bob = await chess_player(session, "bob", rating=2600)
    await enq_chess(session, alice)
    assert (await enq_chess(session, bob)).status == "searching"


async def test_match_econ_reconciles_to_pot(session):
    alice = await cs2_player(session, "alice")
    bob = await cs2_player(session, "bob")
    await enq_cs2(session, alice)
    m = (await enq_cs2(session, bob)).match
    # 10% rake on a $20 pot → $18 prize + $2 rake (integer cents; derived, no odds).
    assert m.pot_cents == 2000
    assert m.prize_cents + m.rake_cents == m.pot_cents
    assert m.prize_cents == 1800 and m.rake_cents == 200


# --- forecast eligibility ------------------------------------------------- #


async def test_lopsided_duel_never_pairs(session):
    strong = await cs2_player(session, "strong", mu=2.0, sigma=0.2)
    weak = await cs2_player(session, "weak", mu=1.0, sigma=0.2)
    await enq_cs2(session, strong)
    # A ~99% forecast sits outside even the widest band.
    assert (await enq_cs2(session, weak)).status == "searching"


async def test_even_duel_pairs(session):
    a = await cs2_player(session, "a", mu=1.0, sigma=0.3)
    b = await cs2_player(session, "b", mu=1.0, sigma=0.3)
    await enq_cs2(session, a)
    assert (await enq_cs2(session, b)).status == "matched"


async def test_crafted_direct_match_cannot_bypass_forecast_window(session):
    strong = await cs2_player(session, "strong", mu=2.0, sigma=0.2)
    weak = await cs2_player(session, "weak", mu=1.0, sigma=0.2)
    r = await enq_cs2(session, strong)
    ticket = r.ticket
    # Taking the other side directly runs the identical checks → rejected.
    with pytest.raises(MatchmakingError) as exc:
        await matchmaking.take_waiting(session, weak, ticket.id)
    assert exc.value.code == "not_pairable"


async def test_widening_ladder_pairs_a_near_miss_after_waiting(session):
    # ~57% forecast: outside 0.05 fresh, inside 0.10 once a ticket has waited >30 s.
    a = await cs2_player(session, "a", mu=1.05, sigma=0.2)
    b = await cs2_player(session, "b", mu=1.0, sigma=0.2)
    r = await enq_cs2(session, a)
    assert (await enq_cs2(session, b)).status == "searching"  # too tight fresh

    # Age A's ticket past the first ladder rung.
    a_ticket = r.ticket
    a_ticket.created_at = datetime.now(UTC) - timedelta(seconds=90)
    await session.flush()

    assert (await matchmaking.poll_status(session, b)).status == "matched"


# --- composite selection -------------------------------------------------- #


async def test_selection_prefers_the_closest_of_two_eligible(session):
    # Two candidates both eligible with the seeker but not with each other, seeded
    # as raw waiting tickets so they don't auto-pair before the seeker arrives.
    seeker = await cs2_player(session, "seeker", mu=1.0, sigma=0.5)
    now = datetime.now(UTC)
    for name, mu in (("near", 1.03), ("far", 1.06)):
        user = await create_user(session, username=name)
        link = await create_linked_account(
            session, user, CS2, profile=cs2_profile(name)
        )
        session.add(
            QueueTicket(
                user_id=user.id,
                linked_account_id=link.id,
                game=CS2,
                market="kd_ratio",
                entry_cents=1000,
                baseline_snapshot={
                    "host_account_id": link.host_account_id,
                    "rating": 1500,
                    "mu": mu,
                    "sigma": 0.5,
                    "n": 15,
                },
                expires_at=now + timedelta(minutes=10),
            )
        )
    await session.flush()

    m = (await enq_cs2(session, seeker)).match
    assert m is not None
    # The seeker paired with "near" (mu 1.03) — the lower composite score — not far.
    paired_ticket = await session.scalar(
        select(QueueTicket).where(
            QueueTicket.state == "matched",
            QueueTicket.user_id != seeker.id,
        )
    )
    assert paired_ticket.baseline_snapshot["mu"] == 1.03


# --- can_pair seam -------------------------------------------------------- #


async def test_self_pair_is_impossible(session):
    alice = await cs2_player(session, "alice")
    await enq_cs2(session, alice)
    # Re-enqueue is idempotent (one ticket), never a self-match.
    assert (await enq_cs2(session, alice)).status == "searching"
    count = await session.scalar(
        select(func.count())
        .select_from(QueueTicket)
        .where(QueueTicket.user_id == alice.id, QueueTicket.state == "waiting")
    )
    assert count == 1


async def test_same_host_account_never_pairs(session):
    a = await cs2_player(session, "a", host="shared_host")
    b = await create_user(session, username="b")
    # Construct two waiting tickets that share a host id in their baselines.
    now = datetime.now(UTC)
    t_a = QueueTicket(
        user_id=a.id,
        linked_account_id=(await matchmaking._require_link(session, a.id, CS2)).id,
        game=CS2,
        market="kd_ratio",
        entry_cents=1000,
        baseline_snapshot={
            "host_account_id": "shared_host",
            "mu": 1.0,
            "sigma": 0.3,
            "n": 15,
        },
        expires_at=now + timedelta(minutes=10),
    )
    t_b = QueueTicket(
        user_id=b.id,
        linked_account_id=t_a.linked_account_id,
        game=CS2,
        market="kd_ratio",
        entry_cents=1000,
        baseline_snapshot={
            "host_account_id": "shared_host",
            "mu": 1.0,
            "sigma": 0.3,
            "n": 15,
        },
        expires_at=now + timedelta(minutes=10),
    )
    assert await matchmaking.can_pair(session, t_a, t_b, now) is False


async def test_provisional_metric_cannot_queue_a_stat_duel(session):
    rookie = await cs2_player(session, "rookie", n=4)  # below the provisional floor
    with pytest.raises(MatchmakingError) as exc:
        await enq_cs2(session, rookie)
    assert exc.value.code == "metric_provisional"


async def test_same_two_accounts_cannot_repair_within_24h(session):
    a = await cs2_player(session, "a")
    b = await cs2_player(session, "b")
    await enq_cs2(session, a)
    m = (await enq_cs2(session, b)).match  # first pairing
    # Terminate that match so both are free to queue again (lifecycle lands next).
    m.state = "CANCELED"
    m.resolved_at = datetime.now(UTC)
    await session.flush()
    # Both re-queue immediately → the 24 h repeat guard keeps them apart.
    await enq_cs2(session, a)
    assert (await enq_cs2(session, b)).status == "searching"


# --- frozen baselines ----------------------------------------------------- #


async def test_baseline_is_frozen_against_later_model_refresh(session):
    a = await cs2_player(session, "a", mu=1.0, sigma=0.3, n=15)
    b = await cs2_player(session, "b", mu=1.0, sigma=0.3, n=15)
    r = await enq_cs2(session, a)  # freezes A's baseline at mu=1.0
    assert r.status == "searching"

    # A's model is refreshed to a wildly different mu after queueing.
    model = await matchmaking._metric_model(session, a.id, CS2, KD)
    model.mu = 5.0
    await session.flush()

    # Pairing must use the FROZEN mu (1.0) → still an even duel → matched.
    m = (await enq_cs2(session, b)).match
    assert m is not None
    a_seat = await session.scalar(
        select(matchmaking.MatchPlayer).where(
            matchmaking.MatchPlayer.match_id == m.id,
            matchmaking.MatchPlayer.user_id == a.id,
        )
    )
    assert a_seat.baseline_snapshot["mu"] == 1.0


# --- race safety (real concurrent transactions) --------------------------- #


@pytest_asyncio.fixture
async def committing_session():
    sm = new_sessionmaker()
    async with sm() as s:
        yield s


async def test_two_concurrent_enqueues_one_waiting_ticket_forms_one_match(
    committing_session,
):
    sm = new_sessionmaker()
    # Seed A (waiting) + two takers B, C, all committed so separate txns see them.
    async with sm() as s:
        a = await cs2_player(s, "racer_a", mu=1.0, sigma=0.3)
        b = await cs2_player(s, "racer_b", mu=1.0, sigma=0.3)
        c = await cs2_player(s, "racer_c", mu=1.0, sigma=0.3)
        await enq_cs2(s, a)  # A waits
        await s.commit()
        b_id, c_id = b.id, c.id

    async def take(user_id):
        async with sm() as s:
            user = await s.get(matchmaking.User, user_id)
            res = await enq_cs2(s, user)
            await s.commit()
            return res.status

    statuses = await asyncio.gather(take(b_id), take(c_id))

    # Exactly one of the two racers pairs with A; the other keeps waiting.
    assert sorted(statuses) == ["matched", "searching"]
    async with sm() as s:
        match_count = await s.scalar(select(func.count()).select_from(Match))
    assert match_count == 1


async def test_enqueue_blocked_by_open_sandbagging_flag(session):
    """A stat-race enqueue honors an existing sandbagging flag (cheap hot-path
    guard, no host call) — backlog · extend the block to H2H stat duels."""
    from moneymatch_api.models.risk import RiskFlag
    from moneymatch_api.services.sandbagging_service import SandbaggingBlockedError

    user = await cs2_player(session, "flagged_duelist")
    session.add(RiskFlag(user_id=user.id, game=CS2, metric=KD, kind="sandbagging"))
    await session.flush()

    with pytest.raises(SandbaggingBlockedError):
        await enq_cs2(session, user, market="kd_ratio")
