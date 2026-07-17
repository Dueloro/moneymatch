"""Ledger reconciliation — the money invariants, checkable from the DB alone.

Two levels (00-README §3.2, 01-architecture §3.3):

- ``check(ref)`` — per-contest conservation:
  ``entries == distributed + rake + still_held`` (an identity the primitives
  must preserve; a mismatch means drift/tampering). A fully settled contest has
  ``still_held == 0``, giving the headline form ``sum(payouts) + rake ==
  sum(entries)``.
- ``check_all()`` — global solvency:
  ``sum(user available + escrow) == promo funding − rake`` plus per-wallet cache
  integrity (each cached balance equals its ledger sum).

Callers (the settlement worker in Phase 3, admin in Phase 6) treat a failure as
**fail-closed**: pause settlement and alert. This module only detects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.wallet import LedgerEntry, PlatformLedgerEntry, Wallet


@dataclass(frozen=True)
class ReconResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)


async def _sum(session: AsyncSession, column, *where) -> int:
    value = await session.scalar(
        select(func.coalesce(func.sum(column), 0)).where(*where)
    )
    return int(value or 0)


async def check(session: AsyncSession, ref_type: str, ref_id: uuid.UUID) -> ReconResult:
    """Assert the conservation identity for a single contest ref."""
    entries = await _sum(
        session,
        LedgerEntry.escrow_delta_cents,
        LedgerEntry.ref_type == ref_type,
        LedgerEntry.ref_id == ref_id,
        LedgerEntry.entry_type == "escrow_hold",
    )
    distributed = await _sum(
        session,
        LedgerEntry.amount_cents,
        LedgerEntry.ref_type == ref_type,
        LedgerEntry.ref_id == ref_id,
        LedgerEntry.entry_type.in_(("payout", "refund")),
    )
    still_held = await _sum(
        session,
        LedgerEntry.escrow_delta_cents,
        LedgerEntry.ref_type == ref_type,
        LedgerEntry.ref_id == ref_id,
    )
    rake = await _sum(
        session,
        PlatformLedgerEntry.amount_cents,
        PlatformLedgerEntry.ref_type == ref_type,
        PlatformLedgerEntry.ref_id == ref_id,
        PlatformLedgerEntry.account == "platform:rake",
    )

    totals = {
        "entries": entries,
        "distributed": distributed,
        "rake": rake,
        "still_held": still_held,
    }
    violations: list[str] = []
    if entries != distributed + rake + still_held:
        violations.append(
            f"conservation breach for {ref_type}:{ref_id} — "
            f"entries={entries} distributed={distributed} rake={rake} "
            f"still_held={still_held}"
        )
    return ReconResult(ok=not violations, violations=violations, totals=totals)


async def check_contests(
    session: AsyncSession,
) -> list[tuple[str, uuid.UUID, ReconResult]]:
    """Per-contest conservation across every match/pool/tournament.

    Returns only the **violating** refs (with their totals) — the admin view
    renders each red with its ledger trail (09-phase-6 · deliverable 2). At MVP
    volume iterating every ref is cheap; a windowed sweep is a later optimization.
    """
    from ..models.play import Match
    from ..models.pools import SoloPool
    from ..models.tournaments import Tournament

    out: list[tuple[str, uuid.UUID, ReconResult]] = []
    for ref_type, model in (
        ("match", Match),
        ("solo_pool", SoloPool),
        ("tournament", Tournament),
    ):
        for ref_id in await session.scalars(select(model.id)):
            result = await check(session, ref_type, ref_id)
            if not result.ok:
                out.append((ref_type, ref_id, result))
    return out


async def check_all(session: AsyncSession) -> ReconResult:
    """Assert global solvency + per-wallet cache integrity across all wallets."""
    user_total = await _sum(session, Wallet.available_cents + Wallet.escrow_cents)
    promo = await _sum(
        session,
        PlatformLedgerEntry.amount_cents,
        PlatformLedgerEntry.account == "platform:promo",
    )
    rake = await _sum(
        session,
        PlatformLedgerEntry.amount_cents,
        PlatformLedgerEntry.account == "platform:rake",
    )

    violations: list[str] = []
    # promo funding == −(promo account balance); solvency: user_total == funding − rake.
    if user_total != -promo - rake:
        violations.append(
            f"solvency breach — user_total={user_total} "
            f"promo_funding={-promo} rake={rake}"
        )

    # Per-wallet: cached available/escrow must equal the ledger sums.
    rows = await session.execute(
        select(
            Wallet.id,
            Wallet.available_cents,
            Wallet.escrow_cents,
            func.coalesce(func.sum(LedgerEntry.amount_cents), 0),
            func.coalesce(func.sum(LedgerEntry.escrow_delta_cents), 0),
        )
        .outerjoin(LedgerEntry, LedgerEntry.wallet_id == Wallet.id)
        .group_by(Wallet.id, Wallet.available_cents, Wallet.escrow_cents)
    )
    for wid, avail, escrow, ledger_avail, ledger_escrow in rows:
        if avail != int(ledger_avail):
            violations.append(
                f"available cache drift on wallet {wid}: "
                f"cached={avail} ledger={int(ledger_avail)}"
            )
        if escrow != int(ledger_escrow):
            violations.append(
                f"escrow cache drift on wallet {wid}: "
                f"cached={escrow} ledger={int(ledger_escrow)}"
            )

    return ReconResult(
        ok=not violations,
        violations=violations,
        totals={"user_total": user_total, "promo_funding": -promo, "rake": rake},
    )
