"""User-facing dispute flow: file (participant, once) + admin resolve + notify."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from moneymatch_api.models.dispute import Dispute
from moneymatch_api.models.notification import Notification
from moneymatch_api.models.play import Match, MatchPlayer
from moneymatch_api.models.user import User

from .conftest import auth_headers
from .factories import create_linked_account, cs2_profile

V1 = "/api/v1"
CS2 = "cs2.faceit"


async def _user(session, auth_id, name, *, role="user"):
    user = User(
        auth_id=auth_id,
        username=name,
        email=f"{name}@t.test",
        residence_state="MA",
        dob_attested_18plus=True,
        status="active",
        role=role,
    )
    session.add(user)
    await session.flush()
    link = await create_linked_account(
        session, user, CS2, host_account_id=f"h_{name}", profile=cs2_profile(name)
    )
    return user, link


async def _settled_match(session, players, *, state="SETTLED", winner=None):
    match = Match(
        game=CS2,
        market="kd_ratio",
        entry_cents=1000,
        rake_bps=1000,
        pot_cents=2000,
        prize_cents=1800,
        rake_cents=200,
        state=state,
        winner_user_id=winner,
        resolved_at=datetime.now(UTC) if state in ("SETTLED", "PUSHED") else None,
    )
    session.add(match)
    await session.flush()
    for user, link in players:
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


async def test_file_dispute_and_dedupe(session, client):
    a, la = await _user(session, "auth_da", "da")
    b, lb = await _user(session, "auth_db", "db")
    match = await _settled_match(session, [(a, la), (b, lb)], winner=b.id)
    await session.commit()

    r = await client.post(
        f"{V1}/play/matches/{match.id}/dispute",
        json={"reason": "My last round wasn't counted."},
        headers=auth_headers("auth_da"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "open"

    # Filing again is a conflict.
    r2 = await client.post(
        f"{V1}/play/matches/{match.id}/dispute",
        json={"reason": "again"},
        headers=auth_headers("auth_da"),
    )
    assert r2.status_code == 409 and r2.json()["code"] == "already_disputed"

    # The filer can read their dispute back.
    r3 = await client.get(
        f"{V1}/play/matches/{match.id}/dispute", headers=auth_headers("auth_da")
    )
    assert r3.status_code == 200 and r3.json()["status"] == "open"


async def test_non_participant_cannot_dispute(session, client):
    a, la = await _user(session, "auth_dc", "dc")
    b, lb = await _user(session, "auth_dd", "dd")
    await _user(session, "auth_de", "de")  # outsider
    match = await _settled_match(session, [(a, la), (b, lb)], winner=a.id)
    await session.commit()

    r = await client.post(
        f"{V1}/play/matches/{match.id}/dispute",
        json={"reason": "not mine"},
        headers=auth_headers("auth_de"),
    )
    assert r.status_code == 403


async def test_cannot_dispute_unsettled(session, client):
    a, la = await _user(session, "auth_df", "df")
    b, lb = await _user(session, "auth_dg", "dg")
    match = await _settled_match(session, [(a, la), (b, lb)], state="ACTIVE")
    await session.commit()

    r = await client.post(
        f"{V1}/play/matches/{match.id}/dispute",
        json={"reason": "too early"},
        headers=auth_headers("auth_df"),
    )
    assert r.status_code == 409 and r.json()["code"] == "not_disputable"


async def test_admin_resolves_and_notifies(session, client):
    a, la = await _user(session, "auth_dh", "dh")
    b, lb = await _user(session, "auth_di", "di")
    await _user(session, "auth_admin_d", "admind", role="admin")
    match = await _settled_match(session, [(a, la), (b, lb)], winner=b.id)
    await session.commit()

    await client.post(
        f"{V1}/play/matches/{match.id}/dispute",
        json={"reason": "regrade please"},
        headers=auth_headers("auth_dh"),
    )
    # Admin lists open disputes and resolves one.
    lst = await client.get(f"{V1}/admin/disputes", headers=auth_headers("auth_admin_d"))
    assert lst.status_code == 200
    dispute_id = next(
        d["id"]
        for d in lst.json()
        if d["ref_type"] == "match" and d["ref_id"] == str(match.id)
    )

    res = await client.post(
        f"{V1}/admin/disputes/{dispute_id}/resolve",
        json={"status": "resolved", "note": "Regraded — your result stands."},
        headers=auth_headers("auth_admin_d"),
    )
    assert res.status_code == 200 and res.json()["status"] == "resolved"

    # The filer got a notification.
    notes = list(
        await session.scalars(
            select(Notification).where(
                Notification.user_id == a.id,
                Notification.kind == "dispute_resolved",
            )
        )
    )
    assert len(notes) == 1
    assert notes[0].payload["status"] == "resolved"

    # And the dispute is closed.
    row = await session.get(Dispute, dispute_id)
    await session.refresh(row)
    assert row.status == "resolved" and row.resolved_at is not None


async def test_file_pool_dispute_participant_only(session, client):
    from datetime import timedelta

    from moneymatch_api.models.pools import SoloEntry, SoloPool

    a, la = await _user(session, "auth_dpa", "dpa")
    now = datetime.now(UTC)
    pool = SoloPool(
        game=CS2,
        metric="cs2_kd_ratio",
        difficulty="medium",
        room_bar=1.25,
        entry_cents=1000,
        rake_bps=1000,
        room_size=1,
        min_entrants=1,
        state="SETTLED",
        window_starts_at=now - timedelta(hours=2),
        window_ends_at=now - timedelta(hours=1),
        resolved_at=now,
    )
    session.add(pool)
    await session.flush()
    session.add(
        SoloEntry(
            pool_id=pool.id,
            user_id=a.id,
            linked_account_id=la.id,
            host_account_id=la.host_account_id,
            personal_bar=1.25,
            status="MISSED",
        )
    )
    await session.commit()

    r = await client.post(
        f"{V1}/disputes",
        json={"ref_type": "pool", "ref_id": str(pool.id), "reason": "bar miscounted"},
        headers=auth_headers("auth_dpa"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["ref_type"] == "pool" and r.json()["status"] == "open"

    # A non-participant can't contest it.
    await _user(session, "auth_dpb", "dpb")
    await session.commit()
    r2 = await client.post(
        f"{V1}/disputes",
        json={"ref_type": "pool", "ref_id": str(pool.id), "reason": "not mine"},
        headers=auth_headers("auth_dpb"),
    )
    assert r2.status_code == 403


async def test_file_tournament_dispute(session, client):
    from datetime import timedelta

    from moneymatch_api.models.tournaments import Tournament, TournamentEntry

    a, la = await _user(session, "auth_dta", "dta")
    now = datetime.now(UTC)
    t = Tournament(
        game=CS2,
        ranking_metric="cs2_kd_ratio",
        entry_cents=1000,
        rake_bps=1000,
        prize_split=[100],
        field_size=4,
        min_field=2,
        min_ranked=1,
        score_matches=3,
        pot_cents=4000,
        prize_cents=3600,
        rake_cents=400,
        state="SETTLED",
        window_starts_at=now - timedelta(hours=2),
        window_ends_at=now - timedelta(hours=1),
        resolved_at=now,
    )
    session.add(t)
    await session.flush()
    session.add(
        TournamentEntry(
            tournament_id=t.id,
            user_id=a.id,
            linked_account_id=la.id,
            host_account_id=la.host_account_id,
            enqueued_at=now,
        )
    )
    await session.commit()

    r = await client.post(
        f"{V1}/disputes",
        json={"ref_type": "tournament", "ref_id": str(t.id), "reason": "wrong rank"},
        headers=auth_headers("auth_dta"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["ref_type"] == "tournament"

    # Read it back through the generic getter.
    g = await client.get(
        f"{V1}/disputes/tournament/{t.id}", headers=auth_headers("auth_dta")
    )
    assert g.status_code == 200 and g.json()["status"] == "open"
