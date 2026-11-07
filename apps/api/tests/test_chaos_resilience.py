"""Chaos / resilience. Builds on the SKIP-LOCKED re-claimability + outage-extension
proofs in test_settlement_worker.py with the two guarantees the phase names
explicitly:
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from moneymatch_api.adapters import registry
from moneymatch_api.constants import MATCH_MAX_LIFETIME_SECONDS
from moneymatch_api.services import reconciliation_service
from moneymatch_api.workers import settlement_worker

from .conftest import new_sessionmaker
from .test_settlement_worker import (
    FakeChessAdapter,
    _balance,
    _match_state,
    setup_active_chess,
)

pytestmark = pytest.mark.asyncio


def _winning_adapter(info) -> FakeChessAdapter:
    return FakeChessAdapter(info["a_host"])


async def test_repeated_cycles_never_double_pay(monkeypatch):
    """A crashed-then-restarted worker re-runs the cycle; settlement is idempotent."""
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: _winning_adapter(info))

    first = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert first.settled == 1
    paid = await _balance(sm, info["a"])
    assert paid == (10800, 0)

    for offset in (6, 7):
        again = await settlement_worker.run_cycle(
            sm, now=info["matched_at"] + timedelta(seconds=offset)
        )
        assert again.settled == 0
    assert await _balance(sm, info["a"]) == paid  # unchanged — no double-pay
    assert await _balance(sm, info["b"]) == (9000, 0)

    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", info["match_id"])
        assert recon.ok and recon.totals["rake"] == 200


async def test_concurrent_workers_settle_exactly_once(monkeypatch):
    """Two workers racing the same due match: SKIP-LOCKED settles it once."""
    sm_a = new_sessionmaker()
    info = await setup_active_chess(sm_a)
    monkeypatch.setattr(registry, "get", lambda gid: _winning_adapter(info))
    sm_b = new_sessionmaker()

    now = info["matched_at"] + timedelta(seconds=5)
    report_a, report_b = await asyncio.gather(
        settlement_worker.run_cycle(sm_a, now=now),
        settlement_worker.run_cycle(sm_b, now=now),
    )

    assert report_a.settled + report_b.settled == 1
    assert await _match_state(sm_a, info["match_id"]) == "SETTLED"
    assert await _balance(sm_a, info["a"]) == (10800, 0)
    assert await _balance(sm_a, info["b"]) == (9000, 0)
    async with sm_a() as s:
        assert (await reconciliation_service.check_all(s)).ok


async def test_persistent_host_outage_refunds_at_hard_ceiling(monkeypatch):
    sm = new_sessionmaker()
    info = await setup_active_chess(sm)
    monkeypatch.setattr(registry, "get", lambda gid: FakeChessAdapter(raise_host=True))

    mid = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(hours=1)
    )
    assert mid.pending == 1
    assert await _balance(sm, info["a"]) == (9000, 1000)

    ceiling = await settlement_worker.run_cycle(
        sm,
        now=info["matched_at"] + timedelta(seconds=MATCH_MAX_LIFETIME_SECONDS + 1),
    )
    assert ceiling.canceled == 1
    assert await _match_state(sm, info["match_id"]) == "CANCELED"
    assert await _balance(sm, info["a"]) == (10000, 0)  # refunded, escrow released
    assert await _balance(sm, info["b"]) == (10000, 0)

    async with sm() as s:
        recon = await reconciliation_service.check(s, "match", info["match_id"])
        assert recon.ok and recon.totals["rake"] == 0  # a refund rakes nothing

    tail = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=MATCH_MAX_LIFETIME_SECONDS + 2)
    )
    assert tail.canceled == 0
    assert await _balance(sm, info["a"]) == (10000, 0)
