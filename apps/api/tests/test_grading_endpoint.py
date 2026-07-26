"""Grading transparency: /play/matches/{id}/grading explains a settled result."""

from __future__ import annotations

from datetime import UTC, datetime

from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.models.user import User

from .conftest import auth_headers
from .factories import create_linked_account, cs2_profile

V1 = "/api/v1"
CS2 = "cs2.faceit"


async def _user(session, auth_id, name):
    user = User(
        auth_id=auth_id,
        username=name,
        email=f"{name}@t.test",
        residence_state="MA",
        dob_attested_18plus=True,
        status="active",
    )
    session.add(user)
    await session.flush()
    link = await create_linked_account(
        session, user, CS2, host_account_id=f"h_{name}", profile=cs2_profile(name)
    )
    return user, link


async def test_grading_explains_a_settled_stat_race(session, client):
    winner, wlink = await _user(session, "auth_gw", "gwin")
    loser, llink = await _user(session, "auth_gl", "glose")
    match = Match(
        game=CS2,
        market="kd_ratio",
        entry_cents=1000,
        rake_bps=1000,
        pot_cents=2000,
        prize_cents=1800,
        rake_cents=200,
        state="SETTLED",
        winner_user_id=winner.id,
        resolved_at=datetime.now(UTC),
        engine_version="stat-1",
        outcome_detail={"metric": "cs2_kd_ratio", "winner": "gwin"},
    )
    session.add(match)
    await session.flush()
    session.add_all(
        [
            MatchPlayer(
                match_id=match.id,
                user_id=winner.id,
                linked_account_id=wlink.id,
                host_account_id=wlink.host_account_id,
                stat_line={"cs2_kd_ratio": 1.8},
            ),
            MatchPlayer(
                match_id=match.id,
                user_id=loser.id,
                linked_account_id=llink.id,
                host_account_id=llink.host_account_id,
                stat_line={"cs2_kd_ratio": 1.1},
            ),
        ]
    )
    await session.commit()

    # The loser sees a transparent "why": the rule, both stat lines, the decision.
    r = await client.get(
        f"{V1}/play/matches/{match.id}/grading", headers=auth_headers("auth_gl")
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "you_lost"
    assert body["settled"] is True
    assert body["winner_username"] == "gwin"
    assert body["your_stat_line"] == {"cs2_kd_ratio": 1.1}
    assert body["opponent_stat_line"] == {"cs2_kd_ratio": 1.8}
    assert body["rule"]  # non-empty resolution note
    assert body["outcome_detail"]["winner"] == "gwin"


async def test_grading_rejects_a_non_participant(session, client):
    winner, wlink = await _user(session, "auth_gw2", "gwin2")
    loser, llink = await _user(session, "auth_gl2", "glose2")
    await _user(session, "auth_outsider", "outsider")
    match = Match(
        game=CS2,
        market="kd_ratio",
        entry_cents=1000,
        rake_bps=1000,
        pot_cents=2000,
        prize_cents=1800,
        rake_cents=200,
        state="SETTLED",
        winner_user_id=winner.id,
        resolved_at=datetime.now(UTC),
    )
    session.add(match)
    await session.flush()
    session.add_all(
        [
            MatchPlayer(
                match_id=match.id,
                user_id=winner.id,
                linked_account_id=wlink.id,
                host_account_id=wlink.host_account_id,
            ),
            MatchPlayer(
                match_id=match.id,
                user_id=loser.id,
                linked_account_id=llink.id,
                host_account_id=llink.host_account_id,
            ),
        ]
    )
    await session.commit()

    r = await client.get(
        f"{V1}/play/matches/{match.id}/grading", headers=auth_headers("auth_outsider")
    )
    assert r.status_code == 403
