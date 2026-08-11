"""CS2 intake: the checks between "a code was pasted" and "a wager pays out".

Each check closes a hole that is otherwise trivially exploitable:

- paste a stranger's good match and get paid for it
- paste your best game from last month
- paste one good match into ten different wagers
- surrender at 3-0 and grade it as a real match

They are cheap, and each is the difference between a wager product and a
donation box.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from moneymatch_api.constants import (
    CS2_MIN_ROUNDS_STANDARD,
    CS2_MIN_ROUNDS_WINGMAN,
    cs2_min_rounds,
)
from moneymatch_api.services import cs2_matches, cs2_submission, gc_client, sharecode
from moneymatch_api.services.cs2_submission import ShareCodeRejected

from .factories import create_linked_account, create_user

pytestmark = pytest.mark.asyncio

MINE = "76561198000000001"
THEIRS = "76561198000000002"


def _code(n: int = 1) -> str:
    return sharecode.encode(n, n * 3, n % 65535)


def _scoreboard(
    *, rounds_a=13, rounds_b=9, roster=(MINE, THEIRS), when=None, players=10
):
    ids = list(roster) + [f"7656119900000{i:04d}" for i in range(players - len(roster))]
    return {
        "matchId": 1,
        "matchTime": int((when or datetime.now(UTC)).timestamp()),
        "map": "de_dust2",
        "scores": {"a": rounds_a, "b": rounds_b},
        "demoUrl": None,
        "expired": True,
        "players": [
            {
                "steamid": sid,
                "team": "a" if i % 2 == 0 else "b",
                "kills": 20 - i,
                "deaths": 10 + i,
                "assists": 3,
                "headshots": 10,
                "mvps": 2,
            }
            for i, sid in enumerate(ids)
        ],
    }


@pytest.fixture
def gc_returns(monkeypatch):
    def _install(payload):
        async def fake_resolve(code):
            return payload

        monkeypatch.setattr(gc_client, "resolve", fake_resolve)

    gc_client.reset_breaker()
    return _install


async def _linked_user(session):
    user = await create_user(session)
    await create_linked_account(session, user, "cs2.steam", host_account_id=MINE)
    await session.commit()
    return user


# --------------------------------------------------------------------------- #
# The metric maths.
# --------------------------------------------------------------------------- #


@pytest.mark.nodb
async def test_metrics_come_straight_off_the_scoreboard():
    metrics = cs2_matches.metrics_from_line(
        {"kills": 24, "deaths": 16, "headshots": 12}
    )
    assert metrics["cs2_kd_ratio"] == pytest.approx(1.5)
    assert metrics["cs2_headshot_pct"] == pytest.approx(50.0)
    assert metrics["cs2_kills"] == 24
    # ADR needs a parsed demo, so it must not appear as if it were gradeable.
    assert "cs2_adr" not in metrics


@pytest.mark.nodb
async def test_a_flawless_game_does_not_divide_by_zero():
    """Zero deaths is a real scoreline, not an error."""
    metrics = cs2_matches.metrics_from_line({"kills": 9, "deaths": 0, "headshots": 4})
    assert metrics["cs2_kd_ratio"] == 9


@pytest.mark.nodb
async def test_zero_kills_is_zero_headshot_percent():
    metrics = cs2_matches.metrics_from_line({"kills": 0, "deaths": 5, "headshots": 0})
    assert metrics["cs2_headshot_pct"] == 0.0


@pytest.mark.nodb
async def test_the_round_floor_follows_the_mode():
    """Wingman is first to 9; Premier and Competitive need 16."""
    assert cs2_min_rounds(10) == CS2_MIN_ROUNDS_STANDARD
    assert cs2_min_rounds(4) == CS2_MIN_ROUNDS_WINGMAN


# --------------------------------------------------------------------------- #
# The four checks.
# --------------------------------------------------------------------------- #


async def test_a_valid_match_is_accepted_and_stored(session, gc_returns):
    user = await _linked_user(session)
    gc_returns(_scoreboard())
    match = await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=_code(11)
    )
    assert match.rounds_total == 22
    assert MINE in match.steam_ids()


async def test_a_malformed_code_never_reaches_the_game_coordinator(session):
    user = await _linked_user(session)
    with pytest.raises(ShareCodeRejected) as excinfo:
        await cs2_submission.submit(
            session, user_id=user.id, steam_id=MINE, share_code="not-a-code"
        )
    assert excinfo.value.code == "sharecode_malformed"


async def test_you_cannot_submit_a_match_you_did_not_play(session, gc_returns):
    """Otherwise I paste a stranger's good game and get paid for it."""
    user = await _linked_user(session)
    gc_returns(_scoreboard(roster=(THEIRS,)))
    with pytest.raises(ShareCodeRejected) as excinfo:
        await cs2_submission.submit(
            session, user_id=user.id, steam_id=MINE, share_code=_code(12)
        )
    assert excinfo.value.code == "sharecode_not_your_match"
    assert "not in that match" in str(excinfo.value).lower()


async def test_you_cannot_submit_a_match_played_before_you_joined(session, gc_returns):
    """Otherwise I paste my best game from last month."""
    user = await _linked_user(session)
    last_month = datetime.now(UTC) - timedelta(days=30)
    gc_returns(_scoreboard(when=last_month))
    with pytest.raises(ShareCodeRejected) as excinfo:
        await cs2_submission.submit(
            session,
            user_id=user.id,
            steam_id=MINE,
            share_code=_code(13),
            joined_at=datetime.now(UTC) - timedelta(hours=1),
        )
    assert excinfo.value.code == "sharecode_predates_wager"


async def test_one_match_cannot_settle_two_wagers(session, gc_returns):
    """The same code twice returns the same stored match, never a second one."""
    user = await _linked_user(session)
    gc_returns(_scoreboard())
    code = _code(14)
    first = await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=code
    )
    second = await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=code
    )
    assert first.id == second.id


async def test_someone_else_cannot_reuse_your_submitted_match(session, gc_returns):
    user = await _linked_user(session)
    gc_returns(_scoreboard())
    code = _code(15)
    await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=code
    )
    with pytest.raises(ShareCodeRejected) as excinfo:
        await cs2_submission.submit(
            session, user_id=uuid.uuid4(), steam_id="76561198000000099", share_code=code
        )
    assert excinfo.value.code == "sharecode_already_used"


async def test_a_surrendered_match_is_not_a_result(session, gc_returns):
    """3-0 and out is not a match anyone should be paid on."""
    user = await _linked_user(session)
    gc_returns(_scoreboard(rounds_a=3, rounds_b=0))
    with pytest.raises(ShareCodeRejected) as excinfo:
        await cs2_submission.submit(
            session, user_id=user.id, steam_id=MINE, share_code=_code(16)
        )
    assert excinfo.value.code == "sharecode_match_too_short"
    assert "at least" in str(excinfo.value)


async def test_a_wingman_match_clears_the_lower_floor(session, gc_returns):
    """2v2 is first to 9, so 9-5 is a complete match."""
    user = await _linked_user(session)
    gc_returns(_scoreboard(rounds_a=9, rounds_b=5, players=4))
    match = await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=_code(17)
    )
    assert match.rounds_total == 14


async def test_an_expired_demo_still_settles(session, gc_returns):
    """Valve keeps demos about a month. The scoreboard is what grades."""
    user = await _linked_user(session)
    gc_returns(_scoreboard())
    match = await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=_code(18)
    )
    assert match.demo_expired is True
    assert match.players  # and the scoreboard is still there


# --------------------------------------------------------------------------- #
# The adapter reads stored matches, so settlement never needs the GC.
# --------------------------------------------------------------------------- #


async def test_a_stored_match_becomes_gradeable_history(session, gc_returns):
    from moneymatch_api.adapters.base import GameFilters
    from moneymatch_api.adapters.cs2_steam import CS2SteamAdapter

    user = await _linked_user(session)
    gc_returns(_scoreboard())
    await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=_code(19)
    )
    await session.commit()

    games = await CS2SteamAdapter().poll_eligible_games(MINE, 0, GameFilters())
    assert len(games) == 1
    assert games[0].metrics["cs2_kd_ratio"] > 0
    assert games[0].id.startswith("CSGO-")


async def test_another_players_match_is_not_your_history(session, gc_returns):
    from moneymatch_api.adapters.base import GameFilters
    from moneymatch_api.adapters.cs2_steam import CS2SteamAdapter

    user = await _linked_user(session)
    gc_returns(_scoreboard())
    await cs2_submission.submit(
        session, user_id=user.id, steam_id=MINE, share_code=_code(20)
    )
    await session.commit()

    games = await CS2SteamAdapter().poll_eligible_games(
        "76561198000000777", 0, GameFilters()
    )
    assert games == []
