"""Admin operator actions on users (09-phase-6 · deliverable 2).

Each mutation here is paired with an `admin_audit` row by its caller (the
`/admin/*` routers, or `scripts/grant_admin.py`). Functions flush, never commit —
the caller owns the transaction so the action and its audit row are atomic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import USER_ROLES, User
from ..models.wallet import LedgerEntry
from . import wallet_service


class AdminActionError(APIError):
    """A rejected admin action (RFC-7807 via APIError)."""


@dataclass(frozen=True)
class ContestRow:
    ref_type: str
    ref_id: uuid.UUID
    game: str
    market: str
    state: str
    entry_cents: int
    payout_cents: int
    created_at: datetime
    resolved_at: datetime | None


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise AdminActionError("user_not_found", "No such user.", status_code=404)
    return user


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    return await session.scalar(select(User).where(User.username == username))


async def set_role(session: AsyncSession, user: User, role: str) -> User:
    """Set a user's role (`user` | `admin`). Grants are audited by the caller."""
    if role not in USER_ROLES:
        raise AdminActionError(
            "invalid_role",
            f"Role must be one of {USER_ROLES}.",
            status_code=422,
        )
    user.role = role
    await session.flush()
    return user


async def search_users(
    session: AsyncSession, q: str | None, *, limit: int = 50
) -> list[User]:
    """Find users by username / email / friend code (or id), for the users table."""
    stmt = select(User).order_by(User.member_since.desc()).limit(limit)
    if q:
        needle = q.strip()
        clauses: list[ColumnElement[bool]] = [
            User.username.ilike(f"%{needle}%"),
            User.email.ilike(f"%{needle}%"),
            User.friend_code.ilike(f"%{needle}%"),
        ]
        # Exact id match too (operators paste a UUID from another view).
        try:
            clauses.append(User.id == uuid.UUID(needle))
        except ValueError:
            pass
        stmt = select(User).where(or_(*clauses)).order_by(User.member_since.desc())
    return list(await session.scalars(stmt))


async def freeze(session: AsyncSession, user: User) -> User:
    """Freeze staking (status → frozen). `assert_can_stake` blocks any non-active
    user; escrow already held still settles normally through the worker."""
    if user.status == "self_excluded":
        raise AdminActionError(
            "self_excluded",
            "A self-excluded user cannot be re-managed via freeze/unfreeze.",
            status_code=409,
        )
    user.status = "frozen"
    await session.flush()
    return user


async def unfreeze(session: AsyncSession, user: User) -> User:
    """Lift a freeze (frozen → active). Self-exclusion is irreversible here."""
    if user.status == "self_excluded":
        raise AdminActionError(
            "self_excluded",
            "Self-exclusion cannot be lifted by an admin.",
            status_code=409,
        )
    user.status = "active"
    await session.flush()
    return user


async def force_unbind(
    session: AsyncSession, linked_account_id: uuid.UUID
) -> LinkedAccount:
    """Remove a host-account binding so it can be re-linked (rebind = admin action,
    audited — 01-architecture §2). Refused with a clean 409 when contest history
    references it (FK RESTRICT); a soft-unbind with history is backlogged."""
    link = await session.get(LinkedAccount, linked_account_id)
    if link is None:
        raise AdminActionError(
            "linked_account_not_found", "No such linked account.", status_code=404
        )
    await session.delete(link)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AdminActionError(
            "unbind_blocked",
            "This account has contest history and cannot be hard-unbound.",
            status_code=409,
            detail={"linked_account_id": str(linked_account_id)},
        ) from exc
    return link


async def user_contests(session: AsyncSession, user_id: uuid.UUID) -> list[ContestRow]:
    """A user's contests across matches / pools / tournaments, newest first."""
    rows: list[ContestRow] = []

    match_q = await session.execute(
        select(Match, MatchPlayer.payout_cents)
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(MatchPlayer.user_id == user_id)
    )
    for match, payout in match_q:
        rows.append(
            ContestRow(
                ref_type="match",
                ref_id=match.id,
                game=match.game,
                market=match.market,
                state=match.state,
                entry_cents=match.entry_cents,
                payout_cents=payout,
                created_at=match.created_at,
                resolved_at=match.resolved_at,
            )
        )

    pool_q = await session.execute(
        select(SoloPool, SoloEntry.payout_cents)
        .join(SoloEntry, SoloEntry.pool_id == SoloPool.id)
        .where(SoloEntry.user_id == user_id)
    )
    for pool, payout in pool_q:
        rows.append(
            ContestRow(
                ref_type="solo_pool",
                ref_id=pool.id,
                game=pool.game,
                market=pool.metric,
                state=pool.state,
                entry_cents=pool.entry_cents,
                payout_cents=payout,
                created_at=pool.created_at,
                resolved_at=pool.resolved_at,
            )
        )

    tour_q = await session.execute(
        select(Tournament, TournamentEntry.payout_cents)
        .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
        .where(TournamentEntry.user_id == user_id)
    )
    for tour, payout in tour_q:
        rows.append(
            ContestRow(
                ref_type="tournament",
                ref_id=tour.id,
                game=tour.game,
                market=tour.ranking_metric,
                state=tour.state,
                entry_cents=tour.entry_cents,
                payout_cents=payout,
                created_at=tour.created_at,
                resolved_at=tour.resolved_at,
            )
        )

    rows.sort(key=lambda r: r.created_at, reverse=True)
    return rows


async def adjust(
    session: AsyncSession,
    user: User,
    *,
    amount_cents: int,
    reason: str,
    admin_id: uuid.UUID,
) -> LedgerEntry:
    """Manual ledger adjustment (reason required; ledger `adjustment` type).

    Positive credits, negative debits — both promo-funded so global solvency
    holds. The `created_by` is the admin's id for the audit trail.
    """
    if amount_cents == 0:
        raise AdminActionError(
            "invalid_amount", "Adjustment must be non-zero.", status_code=422
        )
    if not reason.strip():
        raise AdminActionError(
            "reason_required",
            "A reason is required for a ledger adjustment.",
            status_code=422,
        )
    memo = f"admin adjustment: {reason.strip()}"
    if amount_cents > 0:
        return await wallet_service.credit(
            session, user.id, amount_cents, memo=memo, created_by=str(admin_id)
        )
    return await wallet_service.debit(
        session, user.id, -amount_cents, memo=memo, created_by=str(admin_id)
    )
