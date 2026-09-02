"""Phase 8 test gate — monitoring, anomaly watchdog & ML corpus (DB-backed).

The three properties that make the system operable and trainable at scale:
health numbers roll up, an anomaly routes to review (never a ban), and the corpus
export is pseudonymous and complete.
"""

from __future__ import annotations

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.services.bucketing import markets as mk
from moneymatch_api.services.bucketing import monitoring as mon
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state as stmod
from tests.factories import create_user

MARKET = mk.get("chess.lichess", "blitz", "chess_moves")


def _norm(pid, i, moves):
    return NormGame(
        id=f"{pid}-{i}",
        speed="blitz",
        rated=True,
        created_at_ms=1_760_000_000_000 + i,
        moves=int(moves),
        won=True,
        drawn=False,
        metrics={"chess_moves": float(moves)},
    )


async def _play(session, moves_list):
    u = await create_user(session)
    for i, m in enumerate(moves_list):
        await stmod.record_and_update(session, u.id, "chess.lichess", _norm(u.id, i, m))
    return u


async def _seed_ref(session):
    ref = rf.build_reference(
        [float(v) for v in range(20, 60)], 3, lower_is_better=True
    )
    await stmod.activate_reference(
        session, ref, "chess.lichess", "blitz", "chess_moves", version=1
    )


# --------------------------------------------------------------------------- #
# Health rollup
# --------------------------------------------------------------------------- #


async def test_market_health_reports_the_four_numbers(session):
    await _seed_ref(session)
    for moves in ([25] * 12, [30] * 12, [40] * 12, [50] * 12):
        await _play(session, moves)
    health = await mon.market_health(session, MARKET)
    assert health.rated_players == 4
    assert health.median_matches == 12.0
    assert sum(health.bucket_population.values()) == 4
    # With only 4 players spread across buckets, buckets can't fill a room of 4.
    assert health.starving_buckets  # at least one starving bucket surfaced


# --------------------------------------------------------------------------- #
# Anomaly watchdog — flag + review, never a ban or money move
# --------------------------------------------------------------------------- #


async def test_anomaly_flags_elite_index_on_few_games_for_review(session):
    from sqlalchemy import func, select

    from moneymatch_api.models.bucketing import AuditEvent
    from moneymatch_api.models.wallet import LedgerEntry

    await _seed_ref(session)
    # A healthy population of ordinary players...
    for _ in range(8):
        await _play(session, [40, 42, 38, 41, 39, 43, 40, 42, 41, 39, 40, 42])
    # ...and one account posting an elite (very low) index on just 3 games.
    smurf = await _play(session, [20, 19, 21])

    flags = await mon.detect_anomalies(session, MARKET)
    flagged_ids = {f.player_id for f in flags}
    assert smurf.id in flagged_ids

    # It wrote a review flag...
    n_events = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.event_type == "anomaly_flagged")
    )
    assert n_events >= 1
    # ...and moved NO money (no ledger entries at all).
    n_ledger = await session.scalar(select(func.count()).select_from(LedgerEntry))
    assert n_ledger == 0


async def test_anomaly_quiet_on_small_populations(session):
    await _seed_ref(session)
    await _play(session, [20, 19, 21])  # single account, nothing to compare to
    flags = await mon.detect_anomalies(session, MARKET)
    assert flags == []


# --------------------------------------------------------------------------- #
# ML corpus export — pseudonymous & complete
# --------------------------------------------------------------------------- #


async def test_corpus_export_is_pseudonymous_and_complete(session):
    await _seed_ref(session)
    u = await _play(session, [30, 28, 34, 26, 31])
    corpus = await mon.export_corpus(session, game="chess.lichess")
    assert len(corpus) == 5
    row = corpus[0]
    # Full stat vector + outcome, keyed by the opaque internal id.
    assert set(row) == {
        "player_id",
        "game",
        "mode",
        "created_at_ms",
        "outcome_won",
        "features",
    }
    assert row["player_id"] == str(u.id)
    assert "chess_moves" in row["features"]
    # No PII leaks: the exported keys carry no handle/email/wallet field.
    assert not any(
        k in row for k in ("email", "username", "handle", "auth_id", "wallet_id")
    )


async def test_corpus_size_counts_recorded_matches(session):
    await _seed_ref(session)
    await _play(session, [30, 28, 34])
    assert await mon.corpus_size(session, game="chess.lichess") == 3
    assert await mon.corpus_size(session, game="pubg.steam") == 0
