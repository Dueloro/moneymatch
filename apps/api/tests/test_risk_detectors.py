"""Derived risk detectors (nightly) — the host-free win-streak signal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from moneymatch_api.constants import (
    PAIR_RAKE_CONTESTS_PER_DAY,
    PAIR_RAKE_CONTESTS_PER_WEEK,
    WIN_STREAK_THRESHOLD,
)
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.models.risk import RiskFlag
from moneymatch_api.services import risk_detectors, sandbagging_service

from .factories import create_linked_account, create_user, cs2_profile

pytestmark = pytest.mark.asyncio

CS2 = "cs2.steam"
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


# --------------------------------------------------------------------------- #
# Pair-cap breach detector.
# --------------------------------------------------------------------------- #


async def _pair_match(session, a, la, b, lb, *, when, friendly=False):
    """A rake-bearing (unless friendly) settled match between two users, back-dated
    to `when` so the windowed pair counts are deterministic."""
    # Economics must reconcile (prize + rake == pot): a friendly refunds both
    # entries (full pot as prize, zero rake); a rake-bearing match takes the rake.
    match = Match(
        game=CS2,
        market="kd_ratio",
        entry_cents=1000,
        rake_bps=0 if friendly else 1000,
        pot_cents=2000,
        prize_cents=2000 if friendly else 1800,
        rake_cents=0 if friendly else 200,
        state="SETTLED",
        winner_user_id=a.id,
        friendly=friendly,
        created_at=when,
        resolved_at=when,
    )
    session.add(match)
    await session.flush()
    for user, link in ((a, la), (b, lb)):
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


async def test_pair_cap_breach_over_daily_cap_flags(session):
    a = await create_user(session, username="colluder_a")
    b = await create_user(session, username="colluder_b")
    la, lb = await _link(session, a), await _link(session, b)
    # One more rake-bearing contest than the daily cap allows, all inside a day.
    for i in range(PAIR_RAKE_CONTESTS_PER_DAY + 1):
        await _pair_match(session, a, la, b, lb, when=_BASE + timedelta(hours=i))
    now = _BASE + timedelta(hours=PAIR_RAKE_CONTESTS_PER_DAY + 2)

    assert await risk_detectors.detect_pair_cap_breaches(session, now=now) == 1
    flag = await session.scalar(select(RiskFlag).where(RiskFlag.kind == "pair_cap"))
    assert flag is not None
    # The flag names both accounts (one on the canonical user, the other in detail).
    assert {str(a.id), str(b.id)} == {str(flag.user_id), flag.detail["counterparty"]}
    assert flag.detail["day_count"] == PAIR_RAKE_CONTESTS_PER_DAY + 1
    # Idempotent — an open pair flag is not duplicated on a re-run.
    assert await risk_detectors.detect_pair_cap_breaches(session, now=now) == 0


async def test_pair_at_daily_cap_not_flagged(session):
    a = await create_user(session, username="frequent_a")
    b = await create_user(session, username="frequent_b")
    la, lb = await _link(session, a), await _link(session, b)
    # Exactly at the cap — the cap was honored, so there is no breach to flag.
    for i in range(PAIR_RAKE_CONTESTS_PER_DAY):
        await _pair_match(session, a, la, b, lb, when=_BASE + timedelta(hours=i))
    now = _BASE + timedelta(hours=PAIR_RAKE_CONTESTS_PER_DAY + 1)

    assert await risk_detectors.detect_pair_cap_breaches(session, now=now) == 0


async def test_friendly_matches_are_not_counted(session):
    a = await create_user(session, username="friendly_a")
    b = await create_user(session, username="friendly_b")
    la, lb = await _link(session, a), await _link(session, b)
    # Zero-rake friendlies are excluded from the anti-collusion counter.
    for i in range(PAIR_RAKE_CONTESTS_PER_DAY + 3):
        await _pair_match(
            session, a, la, b, lb, when=_BASE + timedelta(hours=i), friendly=True
        )
    now = _BASE + timedelta(hours=PAIR_RAKE_CONTESTS_PER_DAY + 4)

    assert await risk_detectors.detect_pair_cap_breaches(session, now=now) == 0


async def test_weekly_breach_without_daily_breach_flags(session):
    a = await create_user(session, username="weekly_a")
    b = await create_user(session, username="weekly_b")
    la, lb = await _link(session, a), await _link(session, b)
    # Daily-cap contests spread across enough days to exceed the weekly cap without
    # any single rolling day going over the daily cap.
    days = 4
    for d in range(days):
        for h in range(PAIR_RAKE_CONTESTS_PER_DAY):
            await _pair_match(
                session, a, la, b, lb, when=_BASE - timedelta(days=d, hours=h)
            )
    now = _BASE + timedelta(hours=1)

    assert PAIR_RAKE_CONTESTS_PER_DAY * days > PAIR_RAKE_CONTESTS_PER_WEEK  # 12 > 10
    assert await risk_detectors.detect_pair_cap_breaches(session, now=now) == 1
    flag = await session.scalar(select(RiskFlag).where(RiskFlag.kind == "pair_cap"))
    assert flag.detail["week_count"] == PAIR_RAKE_CONTESTS_PER_DAY * days
