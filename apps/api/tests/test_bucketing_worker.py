"""Wiring test gate — the bucketing worker cycle (DB-backed).

Proves the background loop runs the tested engine end to end: it forms rooms from
the queue, picks up qualifying matches from the log, settles against the one bar
with real wallet money, and refunds at the deadline — and that it is inert unless
the flag is on and halts when settlement is paused.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.constants import FLAG_BUCKETING_ENABLED, FLAG_SETTLEMENT_PAUSED
from moneymatch_api.models.feature_flag import FeatureFlag
from moneymatch_api.services import wallet_service
from moneymatch_api.services.bucketing import config as cfg
from moneymatch_api.services.bucketing import contest as contest_svc
from moneymatch_api.services.bucketing import ingestion
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state as state_svc
from moneymatch_api.workers import bucketing_worker as bw
from tests.conftest import new_sessionmaker
from tests.factories import create_user, create_wallet

CHESS_BLITZ = mk.get("chess.lichess", "blitz", "chess_moves")


def _norm(id, moves, created):
    return NormGame(
        id=id, speed="blitz", rated=True, created_at_ms=created,
        moves=int(moves), won=True, drawn=False,
        metrics={"chess_moves": float(moves)},
    )


async def _set_flag(session, key, enabled):
    row = await session.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
    if row is None:
        session.add(FeatureFlag(key=key, enabled=enabled, payload={}))
    else:
        row.enabled = enabled
    await session.commit()


async def _placed_funded(session, moves, available=100_000):
    u = await create_user(session)
    await create_wallet(session, u, available_cents=available)
    for i, m in enumerate(moves):
        await state_svc.record_and_update(
            session,
            u.id,
            "chess.lichess",
            _norm(f"{u.id}-{i}", m, 1_760_000_000_000 + i),
        )
    return u


async def _seed_ref(session):
    ref = rf.build_reference(
        [float(v) for v in range(20, 60)], 3, lower_is_better=True
    )
    await state_svc.activate_reference(
        session, ref, "chess.lichess", "blitz", "chess_moves", version=1
    )


# --------------------------------------------------------------------------- #
# Flag gating
# --------------------------------------------------------------------------- #


async def test_cycle_is_a_noop_when_flag_off(session):
    sm = new_sessionmaker()
    # Flag defaults off (migration seed) — a cycle does nothing.
    report = await bw.run_bucketing_cycle(sm)
    assert report.ran is False
    assert report.paused is False


async def test_cycle_halts_when_settlement_paused(session):
    await _set_flag(session, FLAG_BUCKETING_ENABLED, True)
    await _set_flag(session, FLAG_SETTLEMENT_PAUSED, True)
    sm = new_sessionmaker()
    report = await bw.run_bucketing_cycle(sm)
    assert report.paused is True
    assert report.ran is False


# --------------------------------------------------------------------------- #
# End-to-end: form → settle with real money
# --------------------------------------------------------------------------- #


async def test_cycle_forms_a_room_then_settles_it(session):
    await _seed_ref(session)
    await _set_flag(session, FLAG_BUCKETING_ENABLED, True)
    sm = new_sessionmaker()

    # Four identical, placed, funded players each stake $5.
    users = []
    for _ in range(4):
        u = await _placed_funded(session, [25] * 12)
        users.append(u)
    for u in users:
        await contest_svc.enter_wager(session, u.id, CHESS_BLITZ, 500)
    await session.commit()

    # Cycle 1: a full room forms; nobody has played yet, so it doesn't settle.
    r1 = await bw.run_bucketing_cycle(sm)
    assert r1.rooms_formed == 1
    assert r1.rooms_settled == 0

    # Read the room's matched_at, then record each member's qualifying match in
    # the log just after it (what the ingest step would have produced live).
    async with sm() as s:
        from moneymatch_api.models.bucket_contest import BucketContest, BucketRoom

        room = await s.scalar(select(BucketRoom))
        members = list(
            await s.scalars(
                select(BucketContest).where(BucketContest.room_id == room.id)
            )
        )
        matched_ms = int(members[0].matched_at.timestamp() * 1000) + 1000
        results = [24, 23, 25, 45]  # three clear the (low) bar, one misses
        for m, moves in zip(members, results, strict=True):
            await ingestion.record_match(
                s, m.player_id, "chess.lichess",
                _norm(f"qual-{m.id}", moves, matched_ms),
            )
        await s.commit()

    # Cycle 2: results are attached from the log and the room settles.
    r2 = await bw.run_bucketing_cycle(sm)
    assert r2.rooms_settled == 1

    # Money conserved: nobody's escrow left hanging; total + rake == start.
    total_available = 0
    async with sm() as s:
        from moneymatch_api.models.bucket_contest import BucketRoom

        room = await s.scalar(select(BucketRoom))
        for u in users:
            w = await wallet_service.get_wallet(s, u.id)
            assert w.escrow_cents == 0
            total_available += w.available_cents
    assert total_available + room.rake_cents == 100_000 * 4
    assert room.status == cfg.ROOM_SETTLED


async def test_cycle_refunds_a_room_that_never_gets_results_by_deadline(session):
    await _seed_ref(session)
    await _set_flag(session, FLAG_BUCKETING_ENABLED, True)
    sm = new_sessionmaker()

    users = [await _placed_funded(session, [25] * 12) for _ in range(4)]
    for u in users:
        await contest_svc.enter_wager(session, u.id, CHESS_BLITZ, 500)
    await session.commit()

    # Form the room now...
    await bw.run_bucketing_cycle(sm)
    async with sm() as s:
        from moneymatch_api.models.bucket_contest import BucketRoom

        room = await s.scalar(select(BucketRoom))
        matched_at = room.created_at

    # ...then run a cycle well past the settle window with no qualifying matches.
    future = matched_at + timedelta(seconds=cfg.BUCKET_SETTLE_WINDOW_SECONDS + 60)
    r = await bw.run_bucketing_cycle(sm, now=future)
    assert r.rooms_settled == 1  # settled == refunded here

    async with sm() as s:
        from moneymatch_api.models.bucket_contest import BucketRoom

        room = await s.scalar(select(BucketRoom))
        assert room.status == cfg.ROOM_REFUNDED
        for u in users:
            w = await wallet_service.get_wallet(s, u.id)
            assert w.available_cents == 100_000  # fully refunded


# --------------------------------------------------------------------------- #
# Ingest leg (via a stub adapter)
# --------------------------------------------------------------------------- #


async def test_ingest_account_records_new_matches(session, monkeypatch):
    from moneymatch_api.adapters import registry
    from moneymatch_api.models.bucketing import MatchStat
    from moneymatch_api.models.linked_account import LinkedAccount

    await _seed_ref(session)
    u = await create_user(session)
    link = LinkedAccount(
        user_id=u.id,
        game="chess.lichess",
        host_account_id="hero",
        host_username="hero",
        link_method="username",
        profile_snapshot={},
        status="active",
    )
    session.add(link)
    await session.flush()

    # Stub the adapter's poll to return two blitz games.
    adapter = registry.get("chess.lichess")

    async def fake_poll(account_id, since_ms, filters):
        return [
            _norm("g1", 30, 1_760_000_000_000),
            _norm("g2", 28, 1_760_000_000_001),
        ]

    monkeypatch.setattr(adapter, "poll_eligible_games", fake_poll)

    n = await bw.ingest_account(session, link)
    assert n == 2
    count = await session.scalar(
        select(MatchStat).where(
            MatchStat.player_id == u.id, MatchStat.game == "chess.lichess"
        )
    )
    assert count is not None
