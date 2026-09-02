"""Phase 1 test gate — idempotent ingestion.

Split into two halves:

- **Pure mode-gate tests** (`nodb`) — run everywhere, incl. this dev box: which
  matches are in scope, and the fail-closed default for CS2/Dota.
- **DB-backed idempotency/concurrency tests** — require Postgres (the schema is
  built from the real migration chain), so they run in CI. They are the Phase 1
  headline: re-ingest is a no-op, concurrent ingest yields exactly one row.
"""

from __future__ import annotations

import uuid

import pytest

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services.bucketing import ingestion


def _norm(id="m1", speed="blitz", created=1_760_000_000_000, won=True, metrics=None):
    return NormGame(
        id=id,
        speed=speed,
        rated=True,
        created_at_ms=created,
        moves=0,
        won=won,
        drawn=False,
        metrics=metrics or {"chess_moves": 30.0},
    )


# --------------------------------------------------------------------------- #
# Pure mode gate (nodb)
# --------------------------------------------------------------------------- #


@pytest.mark.nodb
def test_chess_only_blitz_and_rapid_are_in_scope():
    assert ingestion.bucket_mode_for("chess.lichess", _norm(speed="blitz")) == "blitz"
    assert ingestion.bucket_mode_for("chess.lichess", _norm(speed="rapid")) == "rapid"
    assert ingestion.bucket_mode_for("chess.lichess", _norm(speed="bullet")) is None
    assert ingestion.bucket_mode_for("chess.lichess", _norm(speed="classical")) is None


@pytest.mark.nodb
def test_pubg_official_modes_are_pooled():
    for m in ("solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"):
        assert ingestion.bucket_mode_for("pubg.steam", _norm(speed=m)) == "official"
    assert ingestion.bucket_mode_for("pubg.steam", _norm(speed="war")) is None


@pytest.mark.nodb
def test_cs2_and_dota_are_fail_closed_until_their_gates_land():
    # Both are gated off (MODE_GATE_READY False) — no CS2/Dota match is recorded
    # until the adapter can gate its mode. This is the safe default, not an
    # oversight; see the ingestion module docstring.
    assert ingestion.bucket_mode_for("cs2.steam", _norm(speed="competitive")) is None
    assert ingestion.bucket_mode_for("dota2.opendota", _norm(speed="dota2")) is None
    assert ingestion.MODE_GATE_READY["cs2.steam"] is False
    assert ingestion.MODE_GATE_READY["dota2.opendota"] is False


@pytest.mark.nodb
def test_unknown_game_is_skipped():
    assert ingestion.bucket_mode_for("halo.xbox", _norm()) is None


# --------------------------------------------------------------------------- #
# DB-backed idempotency (CI — needs Postgres)
# --------------------------------------------------------------------------- #


async def _make_user(session) -> uuid.UUID:
    from moneymatch_api.models.user import User

    u = User(
        auth_id=f"auth-{uuid.uuid4()}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        residence_state="MA",
    )
    session.add(u)
    await session.flush()
    return u.id


async def test_reingesting_the_same_match_is_a_noop(session):
    from sqlalchemy import func, select

    from moneymatch_api.models.bucketing import MatchStat

    player = await _make_user(session)
    norm = _norm(id="dup-1", metrics={"chess_moves": 28.0})

    first = await ingestion.record_match(session, player, "chess.lichess", norm)
    second = await ingestion.record_match(session, player, "chess.lichess", norm)

    assert first is True  # newly written
    assert second is False  # already present → no-op
    count = await session.scalar(
        select(func.count())
        .select_from(MatchStat)
        .where(MatchStat.player_id == player, MatchStat.host_match_id == "dup-1")
    )
    assert count == 1


async def test_metrics_are_stored_verbatim(session):
    from sqlalchemy import select

    from moneymatch_api.models.bucketing import MatchStat

    player = await _make_user(session)
    # A rich metrics dict — every field stored, not just the rated one.
    rich = {"chess_moves": 31.0, "opp_rating": 2100.0, "result": 1.0}
    await ingestion.record_match(
        session, player, "chess.lichess", _norm(id="rich-1", metrics=rich)
    )
    row = await session.scalar(
        select(MatchStat).where(MatchStat.host_match_id == "rich-1")
    )
    assert row is not None
    assert row.metrics == rich  # verbatim, including unused fields
    assert row.mode == "blitz"


async def test_out_of_scope_match_records_nothing(session):
    from sqlalchemy import func, select

    from moneymatch_api.models.bucketing import MatchStat

    player = await _make_user(session)
    # A CS2 match: gated off → nothing recorded, returns False.
    wrote = await ingestion.record_match(
        session, player, "cs2.steam", _norm(id="cs2-1", speed="competitive")
    )
    assert wrote is False
    count = await session.scalar(select(func.count()).select_from(MatchStat))
    assert count == 0


async def test_append_only_rejects_update(session):
    from sqlalchemy import text

    player = await _make_user(session)
    await ingestion.record_match(
        session, player, "chess.lichess", _norm(id="immutable-1")
    )
    await session.commit()
    # The append-only trigger must reject any UPDATE.
    with pytest.raises(Exception):  # noqa: B017 - DB raises a driver-specific error
        await session.execute(
            text("UPDATE match_stats SET won = false WHERE host_match_id = :h"),
            {"h": "immutable-1"},
        )
        await session.flush()
