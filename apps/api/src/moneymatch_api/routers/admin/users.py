"""`/admin/users` — find a user, see their whole money trail, and fix things. Search
→ detail (wallet, ledger, linked accounts, limits, contests) → actions: freeze /
unfreeze, force-unbind a linked account, manual ledger adjustment.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...dependencies import AdminUser
from ...models.linked_account import LinkedAccount
from ...models.wallet import LedgerEntry, Limit
from ...schemas.admin import (
    ActionResult,
    AdjustRequest,
    AdminContestRow,
    AdminLedgerPage,
    AdminLimits,
    AdminLinkedAccount,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserSummary,
)
from ...schemas.wallet import LedgerEntryResponse
from ...services import admin_audit_service, admin_service, wallet_service
from ..wallet import ledger_page

router = APIRouter(tags=["admin"])

PAGE_SIZE = 50


def _summary(user, wallet) -> AdminUserSummary:
    return AdminUserSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        friend_code=user.friend_code,
        role=user.role,
        status=user.status,
        residence_state=user.residence_state,
        member_since=user.member_since,
        available_cents=wallet.available_cents if wallet else 0,
        escrow_cents=wallet.escrow_cents if wallet else 0,
    )


@router.get("/users", response_model=AdminUserListResponse)
async def search_users(
    _admin: AdminUser,
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> AdminUserListResponse:
    users = await admin_service.search_users(session, q, limit=PAGE_SIZE)
    out: list[AdminUserSummary] = []
    for user in users:
        wallet = await wallet_service.get_wallet_or_none(session, user.id)
        out.append(_summary(user, wallet))
    return AdminUserListResponse(users=out)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def user_detail(
    user_id: UUID,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> AdminUserDetail:
    user = await admin_service.get_user(session, user_id)
    wallet = await wallet_service.get_wallet_or_none(session, user.id)
    limit = await session.scalar(select(Limit).where(Limit.user_id == user.id))
    links = list(
        await session.scalars(
            select(LinkedAccount).where(LinkedAccount.user_id == user.id)
        )
    )
    contests = await admin_service.user_contests(session, user.id)
    recent: list[LedgerEntry] = []
    if wallet:
        recent = list(
            await session.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.wallet_id == wallet.id)
                .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
                .limit(20)
            )
        )
    return AdminUserDetail(
        id=user.id,
        auth_id=user.auth_id,
        username=user.username,
        email=user.email,
        friend_code=user.friend_code,
        role=user.role,
        status=user.status,
        residence_state=user.residence_state,
        dob_attested_18plus=user.dob_attested_18plus,
        member_since=user.member_since,
        last_seen_at=user.last_seen_at,
        available_cents=wallet.available_cents if wallet else 0,
        escrow_cents=wallet.escrow_cents if wallet else 0,
        lifetime_net_cents=wallet.lifetime_net_cents if wallet else 0,
        limits=AdminLimits.model_validate(limit) if limit else None,
        linked_accounts=[AdminLinkedAccount.model_validate(link) for link in links],
        contests=[
            AdminContestRow(
                ref_type=c.ref_type,
                ref_id=c.ref_id,
                game=c.game,
                market=c.market,
                state=c.state,
                entry_cents=c.entry_cents,
                payout_cents=c.payout_cents,
                created_at=c.created_at,
                resolved_at=c.resolved_at,
            )
            for c in contests
        ],
        recent_ledger=[LedgerEntryResponse.model_validate(r) for r in recent],
    )


@router.post("/users/{user_id}/freeze", response_model=ActionResult)
async def freeze_user(
    user_id: UUID,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ActionResult:
    user = await admin_service.get_user(session, user_id)
    await admin_service.freeze(session, user)
    await admin_audit_service.record(
        session, admin_id=admin.id, action="user.freeze", target=str(user_id)
    )
    return ActionResult(status=user.status)


@router.post("/users/{user_id}/unfreeze", response_model=ActionResult)
async def unfreeze_user(
    user_id: UUID,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ActionResult:
    user = await admin_service.get_user(session, user_id)
    await admin_service.unfreeze(session, user)
    await admin_audit_service.record(
        session, admin_id=admin.id, action="user.unfreeze", target=str(user_id)
    )
    return ActionResult(status=user.status)


@router.post("/users/{user_id}/adjust", response_model=ActionResult)
async def adjust_user(
    user_id: UUID,
    body: AdjustRequest,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ActionResult:
    user = await admin_service.get_user(session, user_id)
    entry = await admin_service.adjust(
        session,
        user,
        amount_cents=body.amount_cents,
        reason=body.reason,
        admin_id=admin.id,
    )
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="ledger.adjust",
        target=str(user_id),
        detail={
            "amount_cents": body.amount_cents,
            "reason": body.reason,
            "ledger_entry_id": str(entry.id),
        },
    )
    return ActionResult(status=user.status)


@router.post("/linked-accounts/{linked_account_id}/unbind", response_model=ActionResult)
async def unbind_linked_account(
    linked_account_id: UUID,
    admin: AdminUser,
    session: AsyncSession = Depends(get_session),
) -> ActionResult:
    link = await admin_service.force_unbind(session, linked_account_id)
    await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="linked_account.unbind",
        target=str(linked_account_id),
        detail={"user_id": str(link.user_id), "game": link.game},
    )
    return ActionResult()


@router.get("/ledger", response_model=AdminLedgerPage)
async def user_ledger(
    _admin: AdminUser,
    user: UUID = Query(..., description="user id"),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> AdminLedgerPage:
    wallet = await wallet_service.get_wallet_or_none(session, user)
    if wallet is None:
        return AdminLedgerPage(entries=[], next_cursor=None)
    rows, next_cursor = await ledger_page(session, wallet.id, cursor, PAGE_SIZE)
    return AdminLedgerPage(
        entries=[LedgerEntryResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
