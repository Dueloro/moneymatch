"""/me.contested_games — per-game "has entered a contest" signal (computed)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.models.user import User

from .conftest import auth_headers
from .factories import create_linked_account

V1 = "/api/v1"


async def test_contested_games_is_per_game(client, session):
    auth = "auth_cg_pergame"
    await client.get(f"{V1}/me", headers=auth_headers(auth))
    user = await session.scalar(select(User).where(User.auth_id == auth))

    # Active on two games, but only ever entered a chess contest.
    await client.patch(
        f"{V1}/me",
        json={"active_games": ["chess.lichess", "cs2.steam"]},
        headers=auth_headers(auth),
    )
    link = await create_linked_account(
        session, user, "chess.lichess", host_account_id="cg_ch"
    )
    now = datetime.now(UTC)
    tour = Tournament(
        game="chess.lichess",
        ranking_metric="chess_moves",
        entry_cents=500,
        rake_bps=1000,
        prize_split=[100],
        field_size=4,
        min_field=2,
        min_ranked=1,
        score_matches=3,
        pot_cents=500,
        window_starts_at=now,
        window_ends_at=now,
    )
    session.add(tour)
    await session.flush()
    session.add(
        TournamentEntry(
            tournament_id=tour.id,
            user_id=user.id,
            linked_account_id=link.id,
            host_account_id="cg_ch",
            enqueued_at=now,
        )
    )
    await session.commit()

    me = (await client.get(f"{V1}/me", headers=auth_headers(auth))).json()
    # Chess entered → contested; CS2 active but never entered → not contested.
    assert me["contested_games"] == ["chess.lichess"]


async def test_contested_games_empty_for_fresh_user(client):
    me = (await client.get(f"{V1}/me", headers=auth_headers("auth_cg_fresh"))).json()
    assert me["contested_games"] == []
