"""Challenges (08-phase-5 · tests): the accept path forms a correct PENDING
match; decline/expiry notify the challenger; invite tokens are single-use, expire,
and survive a fresh-signup accept; an unlinked challengee is prompted to link;
and the pair rake-cap flips a challenge to a zero-rake friendly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.errors import APIError
from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.notification import Notification
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services import challenge_service, friends_service
from moneymatch_api.services.match_states import SETTLED

from .factories import create_linked_account, create_user


async def _any_link(session, user):
    return await session.scalar(
        select(LinkedAccount).where(LinkedAccount.user_id == user.id).limit(1)
    )


pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
KD = "kd_ratio"
ENTRY = 1_000


async def _friends(session, a, b):
    fr = await friends_service.add_friend(session, a, b.username)
    await friends_service.accept_by_id(session, b, fr.id)


async def _pair(session, *, link=True, friends=True):
    a = await create_user(session, username="alice")
    b = await create_user(session, username="bob")
    await create_linked_account(session, a, CS2, host_account_id="host_alice")
    if link:
        await create_linked_account(session, b, CS2, host_account_id="host_bob")
    if friends:
        await _friends(session, a, b)
    return a, b


async def _notifications(session, user_id, kind):
    return list(
        await session.scalars(
            select(Notification).where(
                Notification.user_id == user_id, Notification.kind == kind
            )
        )
    )


async def test_direct_accept_forms_pending_match(session):
    a, b = await _pair(session)
    ch = await challenge_service.create_direct(
        session, a, challengee_id=b.id, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    assert ch.state == "sent"
    # challengee got a challenge_received notification.
    assert len(await _notifications(session, b.id, "challenge_received")) == 1

    match = await challenge_service.accept_direct(session, b, ch.id)
    assert match.state == "PENDING"
    assert match.entry_cents == ENTRY
    assert match.friendly is False
    assert match.rake_cents > 0

    seats = list(
        await session.scalars(
            select(MatchPlayer).where(MatchPlayer.match_id == match.id)
        )
    )
    assert {s.user_id for s in seats} == {a.id, b.id}
    # challenge resolved + linked to the match; challenger notified.
    assert ch.state == "accepted" and ch.match_id == match.id
    assert len(await _notifications(session, a.id, "challenge_accepted")) == 1


async def test_direct_challenge_requires_friendship(session):
    a, b = await _pair(session, friends=False)
    with pytest.raises(APIError) as exc:
        await challenge_service.create_direct(
            session, a, challengee_id=b.id, game=CS2, market_key=KD, entry_cents=ENTRY
        )
    assert exc.value.code == "not_friends"


async def test_self_challenge_rejected(session):
    a, _ = await _pair(session)
    with pytest.raises(APIError) as exc:
        await challenge_service.create_direct(
            session, a, challengee_id=a.id, game=CS2, market_key=KD, entry_cents=ENTRY
        )
    assert exc.value.code == "self_challenge"


async def test_unlinked_challengee_prompts_linking(session):
    a, b = await _pair(session, link=False)
    ch = await challenge_service.create_direct(
        session, a, challengee_id=b.id, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    with pytest.raises(APIError) as exc:
        await challenge_service.accept_direct(session, b, ch.id)
    assert exc.value.code == "needs_link"
    assert exc.value.detail == {"game": CS2}


async def test_decline_notifies_challenger(session):
    a, b = await _pair(session)
    ch = await challenge_service.create_direct(
        session, a, challengee_id=b.id, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    await challenge_service.decline(session, b, ch.id)
    assert ch.state == "declined"
    sys_notes = await _notifications(session, a.id, "system")
    assert any(n.payload.get("event") == "challenge_declined" for n in sys_notes)


async def test_expiry_notifies_and_is_terminal(session):
    a, b = await _pair(session)
    ch = await challenge_service.create_direct(
        session, a, challengee_id=b.id, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    # Force it past its TTL and run the worker's expiry sweep.
    ch.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()
    n = await challenge_service.expire_due(session)
    assert n == 1
    assert ch.state == "expired"
    sys_notes = await _notifications(session, a.id, "system")
    assert any(n.payload.get("event") == "challenge_expired" for n in sys_notes)
    # Accepting an expired challenge fails.
    with pytest.raises(APIError) as exc:
        await challenge_service.accept_direct(session, b, ch.id)
    assert exc.value.code in ("not_open", "expired")


async def test_invite_token_single_use_and_fresh_signup(session):
    a = await create_user(session, username="alice")
    await create_linked_account(session, a, CS2, host_account_id="host_alice")
    ch = await challenge_service.create_invite(
        session, a, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    assert ch.invite_token is not None
    token = ch.invite_token

    # A brand-new user links + accepts — the funnel's end state.
    newcomer = await create_user(session, username="carol")
    await create_linked_account(session, newcomer, CS2, host_account_id="host_carol")
    match = await challenge_service.accept_invite(session, newcomer, token)
    assert match.state == "PENDING"
    assert {s for s in (ch.challenger_id, ch.challengee_id)} == {a.id, newcomer.id}

    # Single-use: a second accept fails.
    other = await create_user(session, username="dave")
    await create_linked_account(session, other, CS2, host_account_id="host_dave")
    with pytest.raises(APIError) as exc:
        await challenge_service.accept_invite(session, other, token)
    assert exc.value.code == "not_open"


async def test_invite_expired_cannot_accept(session):
    a = await create_user(session, username="alice")
    await create_linked_account(session, a, CS2, host_account_id="host_alice")
    ch = await challenge_service.create_invite(
        session, a, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    ch.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()
    b = await create_user(session, username="bob")
    await create_linked_account(session, b, CS2, host_account_id="host_bob")
    with pytest.raises(APIError) as exc:
        await challenge_service.accept_invite(session, b, ch.invite_token)
    assert exc.value.code == "expired"


async def test_preview_token_is_public_shape(session):
    a = await create_user(session, username="alice")
    await create_linked_account(session, a, CS2, host_account_id="host_alice")
    ch = await challenge_service.create_invite(
        session, a, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    preview = await challenge_service.preview_token(session, ch.invite_token)
    assert preview.valid is True
    assert preview.challenger_username == "alice"
    assert preview.challenge.entry_cents == ENTRY


async def _settled_pair_match(session, a, b):
    """Insert a settled, rake-bearing match between two users (cap counter input)."""
    match = Match(
        game=CS2,
        market=KD,
        entry_cents=ENTRY,
        rake_bps=1000,
        pot_cents=2 * ENTRY,
        prize_cents=1800,
        rake_cents=200,
        state=SETTLED,
        friendly=False,
    )
    session.add(match)
    await session.flush()
    for u in (a, b):
        link = await _any_link(session, u)
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=u.id,
                linked_account_id=link.id,
                host_account_id=link.host_account_id,
            )
        )
    await session.flush()
    return match


async def test_pair_rake_cap_flips_to_friendly(session, monkeypatch):
    monkeypatch.setattr(challenge_service, "PAIR_RAKE_CONTESTS_PER_DAY", 2)
    a, b = await _pair(session)

    assert await challenge_service.pair_over_cap(session, a.id, b.id) is False
    await _settled_pair_match(session, a, b)
    await _settled_pair_match(session, a, b)
    assert await challenge_service.pair_over_cap(session, a.id, b.id) is True

    ch = await challenge_service.create_direct(
        session, a, challengee_id=b.id, game=CS2, market_key=KD, entry_cents=ENTRY
    )
    assert ch.friendly is True
    match = await challenge_service.accept_direct(session, b, ch.id)
    assert match.friendly is True
    assert match.rake_cents == 0
    assert match.rake_bps == 0


async def test_friendly_count_excludes_friendlies(session, monkeypatch):
    monkeypatch.setattr(challenge_service, "PAIR_RAKE_CONTESTS_PER_DAY", 1)
    a, b = await _pair(session)
    # A friendly match doesn't count toward the rake cap.
    fmatch = Match(
        game=CS2,
        market=KD,
        entry_cents=ENTRY,
        rake_bps=0,
        pot_cents=2 * ENTRY,
        prize_cents=2 * ENTRY,
        rake_cents=0,
        state=SETTLED,
        friendly=True,
    )
    session.add(fmatch)
    await session.flush()
    for u in (a, b):
        link = await _any_link(session, u)
        session.add(
            MatchPlayer(
                match_id=fmatch.id,
                user_id=u.id,
                linked_account_id=link.id,
                host_account_id=link.host_account_id,
            )
        )
    await session.flush()
    assert await challenge_service.pair_over_cap(session, a.id, b.id) is False
