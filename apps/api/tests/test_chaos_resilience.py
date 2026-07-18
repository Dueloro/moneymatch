"""Chaos / resilience (10-phase-7 §2).

Builds on the SKIP-LOCKED re-claimability + outage-extension proofs in
test_settlement_worker.py with the two guarantees the phase names explicitly:

- A worker that dies mid-settlement never double-pays — the row settles exactly
  once no matter how many cycles (or concurrent workers) run over it.
- A host API that stays down through the whole window strands no escrow: the
  match cancels and fully refunds at the hard ceiling, invariant intact.
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
    FakeCS2Adapter,
    _balance,
    _game,
    _match_state,
    setup_active_cs2,
)

pytestmark = pytest.mark.asyncio


def _winning_adapter(info) -> FakeCS2Adapter:
    ms = int(info["matched_at"].timestamp() * 1000) + 1000
    return FakeCS2Adapter(
        {
            info["a_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.5})],
            info["b_host"]: [_game(ms, metrics={"cs2_kd_ratio": 1.1})],
        }
    )


async def test_repeated_cycles_never_double_pay(monkeypatch):
    """A crashed-then-restarted worker re-runs the cycle; settlement is idempotent."""
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    monkeypatch.setattr(registry, "get", lambda gid: _winning_adapter(info))

    first = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=5)
    )
    assert first.settled == 1
    paid = await _balance(sm, info["a"])
    assert paid == (10800, 0)  # winner +$18

    # Two more full cycles (as if the worker had crashed and been restarted after
    # committing) must not touch a SETTLED match again.
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
    info = await setup_active_cs2(sm_a, market="kd_ratio")
    monkeypatch.setattr(registry, "get", lambda gid: _winning_adapter(info))
    sm_b = new_sessionmaker()

    now = info["matched_at"] + timedelta(seconds=5)
    report_a, report_b = await asyncio.gather(
        settlement_worker.run_cycle(sm_a, now=now),
        settlement_worker.run_cycle(sm_b, now=now),
    )

    # Exactly one of the two cycles booked the settlement; the other skipped.
    assert report_a.settled + report_b.settled == 1
    assert await _match_state(sm_a, info["match_id"]) == "SETTLED"
    assert await _balance(sm_a, info["a"]) == (10800, 0)
    assert await _balance(sm_a, info["b"]) == (9000, 0)
    async with sm_a() as s:
        assert (await reconciliation_service.check_all(s)).ok


async def test_persistent_host_outage_refunds_at_hard_ceiling(monkeypatch):
    """Host down for the entire window → cancel + full refund at the ceiling, no
    stranded escrow, invariant intact."""
    sm = new_sessionmaker()
    info = await setup_active_cs2(sm, market="kd_ratio")
    monkeypatch.setattr(registry, "get", lambda gid: FakeCS2Adapter(raise_host=True))

    # Mid-window with the host down: escrow held, nothing settled (outage extends).
    mid = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(hours=1)
    )
    assert mid.pending == 1
    assert await _balance(sm, info["a"]) == (9000, 1000)  # escrow still held

    # At the hard ceiling the match cancels and both stakes come back in full.
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

    # A further cycle over the CANCELED match changes nothing.
    tail = await settlement_worker.run_cycle(
        sm, now=info["matched_at"] + timedelta(seconds=MATCH_MAX_LIFETIME_SECONDS + 2)
    )
    assert tail.canceled == 0
    assert await _balance(sm, info["a"]) == (10000, 0)
