"""Per-game current win streak (game_stats_service)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.services import game_stats_service

from .factories import chess_profile, create_linked_account, create_user

CHESS = "chess.lichess"
_BASE = datetime(2026, 7, 1, tzinfo=UTC)


async def _link(session, user):
    return await create_linked_account(
        session,
        user,
        CHESS,
        host_account_id=f"host_{user.username}",
        profile=chess_profile(user.username),
    )


async def _settled(session, user, link, *, winner_id, when, game=CHESS):
    match = Match(
        game=game,
        market="win_h2h",
        speed="blitz",
        entry_cents=1000,
        rake_bps=1000,
        pot_cents=2000,
        prize_cents=1800,
        rake_cents=200,
        state="SETTLED",
        winner_user_id=winner_id,
        resolved_at=when,
    )
    session.add(match)
    await session.flush()
    session.add(
        MatchPlayer(
            match_id=match.id,
            user_id=user.id,
            linked_account_id=link.id,
            host_account_id=link.host_account_id,
        )
    )
    await session.flush()
    return match


async def test_counts_consecutive_recent_wins(session):
    user = await create_user(session, username="winner")
    link = await _link(session, user)
    for i in range(3):
        await _settled(
            session, user, link, winner_id=user.id, when=_BASE + timedelta(hours=i)
        )

    assert (await game_stats_service.current_win_streaks(session, user.id)) == {
        CHESS: 3
    }


async def test_recent_loss_resets_streak_to_zero(session):
    user = await create_user(session, username="loser")
    other = await create_user(session, username="rival")
    link = await _link(session, user)
    await _settled(session, user, link, winner_id=user.id, when=_BASE)
    await _settled(
        session, user, link, winner_id=user.id, when=_BASE + timedelta(hours=1)
    )
    await _settled(
        session, user, link, winner_id=other.id, when=_BASE + timedelta(hours=2)
    )

    assert (await game_stats_service.current_win_streaks(session, user.id)) == {
        CHESS: 0
    }


async def test_only_leading_wins_after_last_loss_count(session):
    user = await create_user(session, username="bouncer")
    other = await create_user(session, username="foe")
    link = await _link(session, user)
    await _settled(session, user, link, winner_id=user.id, when=_BASE)
    await _settled(
        session, user, link, winner_id=other.id, when=_BASE + timedelta(hours=1)
    )
    await _settled(
        session, user, link, winner_id=user.id, when=_BASE + timedelta(hours=2)
    )
    await _settled(
        session, user, link, winner_id=user.id, when=_BASE + timedelta(hours=3)
    )

    assert (await game_stats_service.current_win_streaks(session, user.id)) == {
        CHESS: 2
    }
