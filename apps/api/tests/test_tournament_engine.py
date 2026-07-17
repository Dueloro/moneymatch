"""Tournament engine: field formation (dispersion cap), first-N scoring, the
50/30/20 split with ties and forfeits, and the settlement invariant — the ported
`test_tournament.py` spec on integer cents (single-elim cut)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.tournaments import Tournament, TournamentEntry
from moneymatch_api.services import (
    reconciliation_service,
    tournament_engine,
    wallet_service,
)
from moneymatch_api.services.tournament_engine import TournamentGrade

from .factories import (
    create_linked_account,
    create_metric_model,
    create_user,
    create_wallet,
    cs2_profile,
)

pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
KD = "cs2_kd_ratio"


class _FakeAdapter:
    id = CS2
    brokered = False

    async def poll_eligible_games(self, host, since_ms, filters):
        return []


@pytest.fixture(autouse=True)
def _stub_host(monkeypatch):
    from moneymatch_api.adapters import registry

    monkeypatch.setattr(registry, "get", lambda game_id: _FakeAdapter())


async def t_player(session, name, *, mu, sigma=0.30, n=15, fund=10_000):
    user = await create_user(session, username=name)
    await create_linked_account(
        session, user, CS2, host_account_id=f"host_{name}", profile=cs2_profile(name)
    )
    await create_metric_model(session, user, CS2, KD, mu=mu, sigma=sigma, n=n)
    await create_wallet(session, user, available_cents=0)
    await wallet_service.demo_deposit(session, user.id, fund, memo="fund")
    return user


async def enq(session, user, *, entry=1000):
    return await tournament_engine.enqueue(
        session, user, game=CS2, metric=KD, entry_cents=entry
    )


async def _bal(session, user):
    w = await wallet_service.get_wallet(session, user.id)
    return w.available_cents, w.escrow_cents


async def _form(session, n=10, *, mu=1.50):
    """Form a full field of `n` similar players. Returns (tournament, users)."""
    users = []
    for i in range(n):
        users.append(await t_player(session, f"p{i}", mu=mu + i * 0.01))
    for u in users[:-1]:
        await enq(session, u)
    result = await enq(session, users[-1])
    assert result.status == "formed", "field did not form"
    return result.tournament, users


async def _entries(session, tid):
    return list(
        await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == tid)
        )
    )


# --- field formation ------------------------------------------------------ #


async def test_field_forms_under_dispersion_cap(session):
    tournament, users = await _form(session, 10)
    assert tournament.field_size == 10 and tournament.state == "LOCKED"
    # Everyone escrowed the entry.
    for u in users:
        assert (await _bal(session, u))[1] == 1000


async def test_dispersion_cap_refuses_a_lopsided_field(session):
    # Nine tight players + one far outlier → the full field can't form fairly.
    for i in range(9):
        await enq(session, await t_player(session, f"p{i}", mu=1.50 + i * 0.01))
    outlier = await t_player(session, "outlier", mu=5.0, sigma=0.30)
    result = await enq(session, outlier)
    assert result.status == "searching"
    assert (await session.scalar(select(Tournament.id))) is None


# --- first-N scoring ------------------------------------------------------ #


async def test_first_n_average_scores_earliest_three(session):
    tournament, users = await _form(session, 10)
    entries = await _entries(session, tournament.id)
    # Give the first entrant 5 matches; only the first 3 count.
    grades = {}
    grades[entries[0].id] = TournamentGrade(values=[2.0, 2.0, 2.0, 0.0, 0.0])
    for e in entries[1:]:
        grades[e.id] = TournamentGrade(values=[1.0, 1.0, 1.0])
    await tournament_engine.settle_tournament(session, tournament, grades)
    top = next(e for e in await _entries(session, tournament.id) if e.rank == 1)
    assert top.id == entries[0].id
    assert top.score == pytest.approx(2.0)  # mean of first 3, not all 5
    assert top.matches_counted == 3


# --- prize split / invariants --------------------------------------------- #


async def test_top_three_split_50_30_20_and_reconciles(session):
    tournament, users = await _form(session, 10)
    entries = await _entries(session, tournament.id)
    # Distinct descending scores → unambiguous 1..10 ranking.
    grades = {
        e.id: TournamentGrade(values=[2.0 - i * 0.1]) for i, e in enumerate(entries)
    }
    await tournament_engine.settle_tournament(session, tournament, grades)
    assert tournament.state == "SETTLED"
    # Pool $100, rake 10% = $10, net $90 → 45/27/18.
    paid = sorted(
        (e for e in await _entries(session, tournament.id) if e.payout_cents > 0),
        key=lambda e: e.rank,
    )
    assert [e.payout_cents for e in paid] == [4500, 2700, 1800]
    assert tournament.rake_cents == 1000
    recon = await reconciliation_service.check(session, "tournament", tournament.id)
    assert recon.ok
    assert (await reconciliation_service.check_all(session)).ok


async def test_tie_splits_combined_slices_remainder_to_earlier_enqueue(session):
    tournament, users = await _form(session, 10)
    entries = await _entries(session, tournament.id)  # ordered by enqueued_at
    # First two tie for 1st (combined 1st+2nd slices); rest descending.
    grades = {}
    grades[entries[0].id] = TournamentGrade(values=[3.0])
    grades[entries[1].id] = TournamentGrade(values=[3.0])
    for i, e in enumerate(entries[2:], start=2):
        grades[e.id] = TournamentGrade(values=[2.0 - i * 0.1])
    await tournament_engine.settle_tournament(session, tournament, grades)
    fresh = {e.id: e for e in await _entries(session, tournament.id)}
    a, b = fresh[entries[0].id], fresh[entries[1].id]
    # Net $90; 1st+2nd slices = 45+27 = 72 → 36 each; both share rank 1.
    assert a.rank == 1 and b.rank == 1
    assert a.payout_cents + b.payout_cents == 4500 + 2700
    assert abs(a.payout_cents - b.payout_cents) <= 1  # remainder ≤ 1 cent
    recon = await reconciliation_service.check(session, "tournament", tournament.id)
    assert recon.ok


async def test_zero_match_entrant_forfeits_and_is_paid_nothing(session):
    tournament, users = await _form(session, 10)
    entries = await _entries(session, tournament.id)
    grades = {
        e.id: TournamentGrade(values=[1.5 - i * 0.1]) for i, e in enumerate(entries)
    }
    grades[entries[-1].id] = TournamentGrade(values=[])  # played nothing → forfeit
    await tournament_engine.settle_tournament(session, tournament, grades)
    forfeiter = next(
        e for e in await _entries(session, tournament.id) if e.id == entries[-1].id
    )
    assert forfeiter.status == "OUT" and forfeiter.payout_cents == 0
    recon = await reconciliation_service.check(session, "tournament", tournament.id)
    assert recon.ok


async def test_unverifiable_refunded_off_the_top(session):
    tournament, users = await _form(session, 10)
    entries = await _entries(session, tournament.id)
    grades = {
        e.id: TournamentGrade(values=[1.5 - i * 0.1]) for i, e in enumerate(entries)
    }
    grades[entries[-1].id] = TournamentGrade(values=None)  # host couldn't verify
    await tournament_engine.settle_tournament(session, tournament, grades)
    refunded = next(
        e for e in await _entries(session, tournament.id) if e.id == entries[-1].id
    )
    assert refunded.status == "REFUNDED" and refunded.payout_cents == 1000
    recon = await reconciliation_service.check(session, "tournament", tournament.id)
    assert recon.ok


async def test_under_min_ranked_cancels_and_refunds_all(session):
    tournament, users = await _form(session, 10)
    entries = await _entries(session, tournament.id)
    # Only 3 produce a score (< min_ranked 4) → CANCELED, everyone refunded.
    grades = {e.id: TournamentGrade(values=None) for e in entries}
    for e in entries[:3]:
        grades[e.id] = TournamentGrade(values=[1.5])
    await tournament_engine.settle_tournament(session, tournament, grades)
    assert tournament.state == "CANCELED" and tournament.rake_cents == 0
    for u in users:
        assert (await _bal(session, u)) == (10000, 0)
    recon = await reconciliation_service.check(session, "tournament", tournament.id)
    assert recon.ok and recon.totals["rake"] == 0
