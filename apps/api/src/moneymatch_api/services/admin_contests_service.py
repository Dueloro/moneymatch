"""Admin contest views + the two money-fix actions (09-phase-6 · deliverable 2).

- ``list_contests`` — matches / pools / tournaments by state + game.
- ``contest_detail`` — the complete money trail for one ref: participants, user
  ledger rows, platform (rake/promo) rows, adapter evidence, and a live
  reconciliation check.
- ``resettle_match`` — re-runs the exact worker grade+settle path (idempotent:
  a terminal match is a no-op, so it never double-pays).
- ``void_match`` — CANCEL + full refund of the escrowed entries, zero rake, with
  the per-ref conservation invariant asserted on the way out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import APIError
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from ..models.wallet import LedgerEntry, PlatformLedgerEntry, Wallet
from . import match_lifecycle, reconciliation_service
from .match_states import is_terminal

REF_TYPES = ("match", "solo_pool", "tournament")


class ContestActionError(APIError):
    """A rejected admin contest action."""


@dataclass(frozen=True)
class ContestListItem:
    ref_type: str
    ref_id: uuid.UUID
    game: str
    market: str
    state: str
    entry_cents: int
    pot_cents: int
    participants: int
    created_at: datetime
    resolved_at: datetime | None


@dataclass
class ContestDetail:
    ref_type: str
    ref_id: uuid.UUID
    game: str
    market: str
    state: str
    entry_cents: int
    pot_cents: int
    prize_cents: int
    rake_cents: int
    engine_version: str | None
    outcome_detail: dict[str, Any] | None
    created_at: datetime
    resolved_at: datetime | None
    participants: list[dict[str, Any]] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    platform_ledger: list[dict[str, Any]] = field(default_factory=list)
    reconciliation: dict[str, Any] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(UTC)


async def list_contests(
    session: AsyncSession,
    *,
    state: str | None = None,
    game: str | None = None,
    ref_type: str | None = None,
    limit: int = 100,
) -> list[ContestListItem]:
    """Contests across all three products, filtered by state/game, newest first."""
    rows: list[ContestListItem] = []

    if ref_type in (None, "match"):
        stmt_m = select(Match)
        if state:
            stmt_m = stmt_m.where(Match.state == state)
        if game:
            stmt_m = stmt_m.where(Match.game == game)
        for m in await session.scalars(
            stmt_m.order_by(Match.created_at.desc()).limit(limit)
        ):
            count = await session.scalar(
                select(func.count())
                .select_from(MatchPlayer)
                .where(MatchPlayer.match_id == m.id)
            )
            rows.append(
                ContestListItem(
                    ref_type="match",
                    ref_id=m.id,
                    game=m.game,
                    market=m.market,
                    state=m.state,
                    entry_cents=m.entry_cents,
                    pot_cents=m.pot_cents,
                    participants=int(count or 0),
                    created_at=m.created_at,
                    resolved_at=m.resolved_at,
                )
            )

    if ref_type in (None, "solo_pool"):
        stmt_p = select(SoloPool)
        if state:
            stmt_p = stmt_p.where(SoloPool.state == state)
        if game:
            stmt_p = stmt_p.where(SoloPool.game == game)
        for p in await session.scalars(
            stmt_p.order_by(SoloPool.created_at.desc()).limit(limit)
        ):
            count = await session.scalar(
                select(func.count())
                .select_from(SoloEntry)
                .where(SoloEntry.pool_id == p.id)
            )
            rows.append(
                ContestListItem(
                    ref_type="solo_pool",
                    ref_id=p.id,
                    game=p.game,
                    market=p.metric,
                    state=p.state,
                    entry_cents=p.entry_cents,
                    pot_cents=p.pot_cents,
                    participants=int(count or 0),
                    created_at=p.created_at,
                    resolved_at=p.resolved_at,
                )
            )

    if ref_type in (None, "tournament"):
        stmt_t = select(Tournament)
        if state:
            stmt_t = stmt_t.where(Tournament.state == state)
        if game:
            stmt_t = stmt_t.where(Tournament.game == game)
        for t in await session.scalars(
            stmt_t.order_by(Tournament.created_at.desc()).limit(limit)
        ):
            count = await session.scalar(
                select(func.count())
                .select_from(TournamentEntry)
                .where(TournamentEntry.tournament_id == t.id)
            )
            rows.append(
                ContestListItem(
                    ref_type="tournament",
                    ref_id=t.id,
                    game=t.game,
                    market=t.ranking_metric,
                    state=t.state,
                    entry_cents=t.entry_cents,
                    pot_cents=t.pot_cents,
                    participants=int(count or 0),
                    created_at=t.created_at,
                    resolved_at=t.resolved_at,
                )
            )

    rows.sort(key=lambda r: r.created_at, reverse=True)
    return rows[:limit]


async def _usernames(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: name for uid, name in rows}


async def _money_trail(
    session: AsyncSession, ref_type: str, ref_id: uuid.UUID
) -> tuple[list[dict], list[dict]]:
    """User ledger rows (with the owning user) + platform rows for one ref."""
    ledger_rows = await session.execute(
        select(LedgerEntry, Wallet.user_id, User.username)
        .join(Wallet, Wallet.id == LedgerEntry.wallet_id)
        .join(User, User.id == Wallet.user_id)
        .where(LedgerEntry.ref_type == ref_type, LedgerEntry.ref_id == ref_id)
        .order_by(LedgerEntry.created_at.asc())
    )
    ledger = [
        {
            "id": str(entry.id),
            "user_id": str(user_id),
            "username": username,
            "entry_type": entry.entry_type,
            "amount_cents": entry.amount_cents,
            "escrow_delta_cents": entry.escrow_delta_cents,
            "balance_after_cents": entry.balance_after_cents,
            "memo": entry.memo,
            "created_by": entry.created_by,
            "created_at": entry.created_at.isoformat(),
        }
        for entry, user_id, username in ledger_rows
    ]
    platform_rows = await session.scalars(
        select(PlatformLedgerEntry)
        .where(
            PlatformLedgerEntry.ref_type == ref_type,
            PlatformLedgerEntry.ref_id == ref_id,
        )
        .order_by(PlatformLedgerEntry.created_at.asc())
    )
    platform = [
        {
            "account": p.account,
            "amount_cents": p.amount_cents,
            "memo": p.memo,
            "created_at": p.created_at.isoformat(),
        }
        for p in platform_rows
    ]
    return ledger, platform


async def contest_detail(
    session: AsyncSession, ref_type: str, ref_id: uuid.UUID
) -> ContestDetail:
    if ref_type == "match":
        detail = await _match_detail(session, ref_id)
    elif ref_type == "solo_pool":
        detail = await _pool_detail(session, ref_id)
    elif ref_type == "tournament":
        detail = await _tournament_detail(session, ref_id)
    else:
        raise ContestActionError(
            "invalid_ref_type", f"ref_type must be one of {REF_TYPES}.", status_code=422
        )
    detail.ledger, detail.platform_ledger = await _money_trail(
        session, ref_type, ref_id
    )
    recon = await reconciliation_service.check(session, ref_type, ref_id)
    detail.reconciliation = {
        "ok": recon.ok,
        "violations": recon.violations,
        "totals": recon.totals,
    }
    return detail


async def _match_detail(session: AsyncSession, match_id: uuid.UUID) -> ContestDetail:
    match = await session.get(Match, match_id)
    if match is None:
        raise ContestActionError("contest_not_found", "No such match.", status_code=404)
    seats = list(
        await session.scalars(
            select(MatchPlayer).where(MatchPlayer.match_id == match_id)
        )
    )
    names = await _usernames(session, [s.user_id for s in seats])
    participants = [
        {
            "user_id": str(s.user_id),
            "username": names.get(s.user_id),
            "host_account_id": s.host_account_id,
            "color": s.color,
            "confirmed_at": s.confirmed_at.isoformat() if s.confirmed_at else None,
            "payout_cents": s.payout_cents,
            "stat_line": s.stat_line,
        }
        for s in seats
    ]
    return ContestDetail(
        ref_type="match",
        ref_id=match.id,
        game=match.game,
        market=match.market,
        state=match.state,
        entry_cents=match.entry_cents,
        pot_cents=match.pot_cents,
        prize_cents=match.prize_cents,
        rake_cents=match.rake_cents,
        engine_version=match.engine_version,
        outcome_detail=match.outcome_detail,
        created_at=match.created_at,
        resolved_at=match.resolved_at,
        participants=participants,
    )


async def _pool_detail(session: AsyncSession, pool_id: uuid.UUID) -> ContestDetail:
    pool = await session.get(SoloPool, pool_id)
    if pool is None:
        raise ContestActionError("contest_not_found", "No such pool.", status_code=404)
    entries = list(
        await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool_id))
    )
    names = await _usernames(session, [e.user_id for e in entries])
    participants = [
        {
            "user_id": str(e.user_id),
            "username": names.get(e.user_id),
            "personal_bar": e.personal_bar,
            "status": e.status,
            "payout_cents": e.payout_cents,
            "telemetry": e.telemetry,
        }
        for e in entries
    ]
    return ContestDetail(
        ref_type="solo_pool",
        ref_id=pool.id,
        game=pool.game,
        market=pool.metric,
        state=pool.state,
        entry_cents=pool.entry_cents,
        pot_cents=pool.pot_cents,
        prize_cents=pool.prize_cents,
        rake_cents=pool.rake_cents,
        engine_version=pool.engine_version,
        outcome_detail=pool.outcome_detail,
        created_at=pool.created_at,
        resolved_at=pool.resolved_at,
        participants=participants,
    )


async def _tournament_detail(session: AsyncSession, tid: uuid.UUID) -> ContestDetail:
    tour = await session.get(Tournament, tid)
    if tour is None:
        raise ContestActionError(
            "contest_not_found", "No such tournament.", status_code=404
        )
    entries = list(
        await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == tid)
        )
    )
    names = await _usernames(session, [e.user_id for e in entries])
    participants = [
        {
            "user_id": str(e.user_id),
            "username": names.get(e.user_id),
            "score": e.score,
            "rank": e.rank,
            "status": e.status,
            "payout_cents": e.payout_cents,
        }
        for e in entries
    ]
    return ContestDetail(
        ref_type="tournament",
        ref_id=tour.id,
        game=tour.game,
        market=tour.ranking_metric,
        state=tour.state,
        entry_cents=tour.entry_cents,
        pot_cents=tour.pot_cents,
        prize_cents=tour.prize_cents,
        rake_cents=tour.rake_cents,
        engine_version=tour.engine_version,
        outcome_detail=tour.outcome_detail,
        created_at=tour.created_at,
        resolved_at=tour.resolved_at,
        participants=participants,
    )


# --------------------------------------------------------------------------- #
# Money-fix actions (matches).
# --------------------------------------------------------------------------- #


async def resettle_match(
    session: AsyncSession, match_id: uuid.UUID, *, now: datetime | None = None
) -> str:
    """Re-run the worker's grade+settle path for a match, under a row lock.

    Idempotent: a terminal match is a no-op (the lifecycle rejects a transition
    out of a terminal state), so a double-fire never double-pays.
    """
    from ..workers import settlement_worker  # lazy: worker imports services

    match = await session.scalar(
        select(Match).where(Match.id == match_id).with_for_update()
    )
    if match is None:
        raise ContestActionError("contest_not_found", "No such match.", status_code=404)
    if is_terminal(match.state):
        return match.state  # nothing to do; idempotent
    return await settlement_worker.resolve_match(session, match, now or _now())


async def void_match(
    session: AsyncSession, match_id: uuid.UUID, *, reason: str
) -> Match:
    """Void a match: CANCEL + full refund of the escrowed entries, zero rake."""
    match = await session.scalar(
        select(Match).where(Match.id == match_id).with_for_update()
    )
    if match is None:
        raise ContestActionError("contest_not_found", "No such match.", status_code=404)
    if is_terminal(match.state):
        raise ContestActionError(
            "already_terminal",
            "This match is already settled; use a manual adjustment instead.",
            status_code=409,
        )
    if match.state == "PENDING":
        return await match_lifecycle.cancel_pending(session, match, reason=reason)
    return await match_lifecycle.settle(
        session,
        match,
        match_lifecycle.SettlementResult(
            kind=match_lifecycle.CANCEL,
            outcome_detail={"reason": reason, "voided_by": "admin"},
            engine_version="admin-void",
        ),
    )
