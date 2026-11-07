"""DB-backed matchmaking: compatibility, the Elo band and its widening, selection,
the anti-collusion `can_pair` seam, race-safety, and frozen baselines.
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
from .factories import chess_profile, create_linked_account, create_user

pytestmark = pytest.mark.asyncio

CHESS = "chess.lichess"


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


async def enq_chess(session, user, *, entry=1000, speed="blitz"):
    return await matchmaking.enqueue(
        session, user, game=CHESS, market_key="win_h2h", entry_cents=entry, speed=speed
    )


def _ticket(user, link, *, rating, now, host=None):
    return QueueTicket(
        user_id=user.id,
        linked_account_id=link.id,
        game=CHESS,
        market="win_h2h",
        speed="blitz",
        entry_cents=1000,
        rating=rating,
        baseline_snapshot={
            "host_account_id": host or link.host_account_id,
            "rating": rating,
        },
        expires_at=now + timedelta(minutes=10),
    )


# --- pairing basics ------------------------------------------------------- #


async def test_first_searches_second_matches(session):
    alice = await chess_player(session, "alice")
    bob = await chess_player(session, "bob")
    assert (await enq_chess(session, alice)).status == "searching"
    r = await enq_chess(session, bob)
    assert r.status == "matched"
    assert r.match.state == "PENDING" and r.match.entry_cents == 1000
    # Alice now polls to matched.
    assert (await matchmaking.poll_status(session, alice)).status == "matched"


async def test_incompatible_entry_does_not_pair(session):
    alice = await chess_player(session, "alice")
    bob = await chess_player(session, "bob")
    await enq_chess(session, alice, entry=1000)
    assert (await enq_chess(session, bob, entry=2500)).status == "searching"


async def test_different_time_control_does_not_pair(session):
    alice = await chess_player(session, "alice")
    bob = await chess_player(session, "bob")
    await enq_chess(session, alice, speed="blitz")
    assert (await enq_chess(session, bob, speed="rapid")).status == "searching"


async def test_chess_assigns_colors(session):
    alice = await chess_player(session, "alice", rating=1500)
    bob = await chess_player(session, "bob", rating=1520)
    await enq_chess(session, alice)
    m = (await enq_chess(session, bob)).match
    players = list(
        await session.scalars(
            select(matchmaking.MatchPlayer).where(
                matchmaking.MatchPlayer.match_id == m.id
            )
        )
    )
    assert {p.color for p in players} == {"white", "black"}


async def test_match_econ_reconciles_to_pot(session):
    alice = await chess_player(session, "alice")
    bob = await chess_player(session, "bob")
    await enq_chess(session, alice)
    m = (await enq_chess(session, bob)).match
    # 10% rake on a $20 pot → $18 prize + $2 rake (integer cents; derived, no odds).
    assert m.pot_cents == 2000
    assert m.prize_cents + m.rake_cents == m.pot_cents
    assert m.prize_cents == 1800 and m.rake_cents == 200


# --- Elo band ------------------------------------------------------------- #


async def test_chess_far_rating_does_not_pair_fresh(session):
    alice = await chess_player(session, "alice", rating=1200)
    bob = await chess_player(session, "bob", rating=2600)
    await enq_chess(session, alice)
    assert (await enq_chess(session, bob)).status == "searching"


async def test_crafted_direct_match_cannot_bypass_the_band(session):
    strong = await chess_player(session, "strong", rating=2600)
    weak = await chess_player(session, "weak", rating=1200)
    r = await enq_chess(session, strong)
    # Taking the other side directly runs the identical checks → rejected.
    with pytest.raises(MatchmakingError) as exc:
        await matchmaking.take_waiting(session, weak, r.ticket.id)
    assert exc.value.code == "not_pairable"


async def test_widening_band_pairs_a_near_miss_after_waiting(session):
    # 200 Elo apart: outside the fresh 100 band, inside once a ticket has waited.
    a = await chess_player(session, "a", rating=1700)
    b = await chess_player(session, "b", rating=1500)
    r = await enq_chess(session, a)
    assert (await enq_chess(session, b)).status == "searching"  # too tight fresh

    r.ticket.created_at = datetime.now(UTC) - timedelta(seconds=90)
    await session.flush()

    assert (await matchmaking.poll_status(session, b)).status == "matched"


# --- selection ------------------------------------------------------------ #


async def test_selection_prefers_the_closest_of_two_eligible(session):
    # Seeded as raw waiting tickets so they don't auto-pair before the seeker.
    seeker = await chess_player(session, "seeker", rating=1500)
    now = datetime.now(UTC)
    for name, rating in (("near", 1530), ("far", 1560)):
        user = await create_user(session, username=name)
        link = await create_linked_account(
            session, user, CHESS, profile=chess_profile(name, rating=rating)
        )
        session.add(_ticket(user, link, rating=rating, now=now))
    await session.flush()

    m = (await enq_chess(session, seeker)).match
    assert m is not None
    paired_ticket = await session.scalar(
        select(QueueTicket).where(
            QueueTicket.state == "matched",
            QueueTicket.user_id != seeker.id,
        )
    )
    assert paired_ticket.baseline_snapshot["rating"] == 1530


# --- can_pair seam -------------------------------------------------------- #


async def test_self_pair_is_impossible(session):
    alice = await chess_player(session, "alice")
    await enq_chess(session, alice)
    # Re-enqueue is idempotent (one ticket), never a self-match.
    assert (await enq_chess(session, alice)).status == "searching"
    count = await session.scalar(
        select(func.count())
        .select_from(QueueTicket)
        .where(QueueTicket.user_id == alice.id, QueueTicket.state == "waiting")
    )
    assert count == 1


async def test_same_host_account_never_pairs(session):
    a = await chess_player(session, "a", host="shared_host")
    b = await create_user(session, username="b")
    now = datetime.now(UTC)
    link = await matchmaking._require_link(session, a.id, CHESS)
    t_a = _ticket(a, link, rating=1500, now=now, host="shared_host")
    t_b = _ticket(b, link, rating=1500, now=now, host="shared_host")
    assert await matchmaking.can_pair(session, t_a, t_b, now) is False


async def test_same_two_accounts_cannot_repair_within_24h(session):
    a = await chess_player(session, "a")
    b = await chess_player(session, "b")
    await enq_chess(session, a)
    m = (await enq_chess(session, b)).match  # first pairing
    m.state = "CANCELED"
    m.resolved_at = datetime.now(UTC)
    await session.flush()
    # Both re-queue immediately → the 24 h repeat guard keeps them apart.
    await enq_chess(session, a)
    assert (await enq_chess(session, b)).status == "searching"


# --- frozen baselines ----------------------------------------------------- #


async def test_baseline_is_frozen_against_later_profile_refresh(session):
    a = await chess_player(session, "a", rating=1500)
    b = await chess_player(session, "b", rating=1500)
    r = await enq_chess(session, a)  # freezes A's baseline at 1500
    assert r.status == "searching"

    # A's profile is refreshed to a wildly different rating after queueing.
    link = await matchmaking._require_link(session, a.id, CHESS)
    link.profile_snapshot = chess_profile("a", rating=2600).model_dump()
    await session.flush()

    # Pairing must use the FROZEN rating → still inside the band → matched.
    m = (await enq_chess(session, b)).match
    assert m is not None
    a_seat = await session.scalar(
        select(matchmaking.MatchPlayer).where(
            matchmaking.MatchPlayer.match_id == m.id,
            matchmaking.MatchPlayer.user_id == a.id,
        )
    )
    assert a_seat.baseline_snapshot["rating"] == 1500


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
        a = await chess_player(s, "racer_a")
        b = await chess_player(s, "racer_b")
        c = await chess_player(s, "racer_c")
        await enq_chess(s, a)  # A waits
        await s.commit()
        b_id, c_id = b.id, c.id

    async def take(user_id):
        async with sm() as s:
            user = await s.get(matchmaking.User, user_id)
            res = await enq_chess(s, user)
            await s.commit()
            return res.status

    statuses = await asyncio.gather(take(b_id), take(c_id))

    # Exactly one of the two racers pairs with A; the other keeps waiting.
    assert sorted(statuses) == ["matched", "searching"]
    async with sm() as s:
        match_count = await s.scalar(select(func.count()).select_from(Match))
    assert match_count == 1


async def test_excluded_state_is_geo_blocked_from_h2h(session):
    """A resident of a geo-fenced state is refused before queueing (parity with
    pools/tournaments)."""
    from sqlalchemy import text

    from moneymatch_api.services.geo_service import RegionBlockedError

    await session.execute(text("DELETE FROM feature_flags WHERE key = 'geo_config'"))
    await session.execute(
        text(
            "INSERT INTO feature_flags (key, enabled, payload) "
            "VALUES ('geo_config', true, cast(:p as jsonb))"
        ),
        {"p": '{"excluded_states": ["FL"]}'},
    )
    await session.flush()

    user = await create_user(session, username="flguy", residence_state="FL")
    await create_linked_account(session, user, CHESS, profile=chess_profile("flguy"))

    with pytest.raises(RegionBlockedError):
        await enq_chess(session, user)
