"""Derived risk detectors (nightly) — the host-free win-streak signal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.constants import WIN_STREAK_THRESHOLD
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.models.risk import RiskFlag
from moneymatch_api.services import risk_detectors, sandbagging_service

from .factories import create_linked_account, create_user, cs2_profile

pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
_BASE = datetime(2026, 7, 1, tzinfo=UTC)


async def _link(session, user):
    return await create_linked_account(
        session,
        user,
        CS2,
        host_account_id=f"host_{user.username}",
        profile=cs2_profile(user.username),
    )


async def _settled(session, user, link, *, winner_id, when):
    match = Match(
        game=CS2,
        market="kd_ratio",
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


async def test_win_streak_flags_after_threshold(session):
    user = await create_user(session, username="streaker")
    link = await _link(session, user)
    for i in range(WIN_STREAK_THRESHOLD):
        await _settled(
            session, user, link, winner_id=user.id, when=_BASE + timedelta(hours=i)
        )

    assert await risk_detectors.detect_win_streaks(session) == 1
    flag = await session.scalar(select(RiskFlag).where(RiskFlag.user_id == user.id))
    assert flag.kind == "win_streak"
    assert flag.detail["streak"] == WIN_STREAK_THRESHOLD
    # Idempotent — an open flag is not duplicated on a re-run.
    assert await risk_detectors.detect_win_streaks(session) == 0


async def test_recent_loss_breaks_the_streak(session):
    user = await create_user(session, username="cooling")
    rival = await create_user(session, username="rival")
    link = await _link(session, user)
    for i in range(WIN_STREAK_THRESHOLD - 1):
        await _settled(
            session, user, link, winner_id=user.id, when=_BASE + timedelta(hours=i)
        )
    # Most recent settled match is a loss → the window isn't an unbroken run.
    await _settled(
        session,
        user,
        link,
        winner_id=rival.id,
        when=_BASE + timedelta(hours=WIN_STREAK_THRESHOLD),
    )
    assert await risk_detectors.detect_win_streaks(session) == 0


async def test_win_streak_flag_never_blocks_wagers(session):
    user = await create_user(session, username="hot_hand")
    session.add(RiskFlag(user_id=user.id, game=CS2, metric="*", kind="win_streak"))
    await session.flush()
    # is_flagged is sandbagging-only, so the informational streak flag is ignored.
    blocked = await sandbagging_service.is_flagged(
        session, user.id, CS2, "cs2_kd_ratio"
    )
    assert blocked is False
