"""New-user provisioning: DEMO wallet + default limits + $1000 signup grant,
funded from platform:promo, idempotent across logins."""

from __future__ import annotations

from sqlalchemy import func, select

from moneymatch_api.models.user import User
from moneymatch_api.models.wallet import (
    LedgerEntry,
    Limit,
    PlatformLedgerEntry,
    Wallet,
)

from .conftest import auth_headers


async def _wallet_for(session, auth_id: str) -> Wallet:
    user = await session.scalar(select(User).where(User.auth_id == auth_id))
    return await session.scalar(select(Wallet).where(Wallet.user_id == user.id))


async def test_first_authed_call_grants_1000_and_funds_promo(client, session):
    resp = await client.get("/api/v1/me", headers=auth_headers("newbie"))
    assert resp.status_code == 200

    wallet = await _wallet_for(session, "newbie")
    assert wallet.available_cents == 100_000
    assert wallet.escrow_cents == 0

    grants = await session.scalars(
        select(LedgerEntry).where(
            LedgerEntry.wallet_id == wallet.id,
            LedgerEntry.entry_type == "demo_deposit",
        )
    )
    grants = list(grants)
    assert len(grants) == 1
    assert grants[0].amount_cents == 100_000
    assert grants[0].memo == "signup grant"

    promo = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.account == "platform:promo"
        )
    )
    assert promo == -100_000  # promo funded exactly the grant


async def test_friend_code_collision_retries(session, monkeypatch):
    """A friend_code unique collision must be retried, not surfaced as a 500."""
    from moneymatch_api.auth import AuthedIdentity
    from moneymatch_api.services import user_service

    # A committed user occupies MM-CLASH1 so it survives the retry rollback.
    existing = User(auth_id="fc_existing", friend_code="MM-CLASH1")
    session.add(existing)
    await session.commit()

    # First generated code collides; the retry mints a fresh one and provisions.
    codes = iter(["MM-CLASH1", "MM-FRESH1"])
    monkeypatch.setattr(user_service, "gen_friend_code", lambda: next(codes))

    user = await user_service.get_or_create_user(
        session, AuthedIdentity(auth_id="fc_new", email=None)
    )

    assert user.friend_code == "MM-FRESH1"
    # Fully provisioned despite the collision (wallet grant landed).
    wallet = await _wallet_for(session, "fc_new")
    assert wallet.available_cents == 100_000


async def test_default_limits_provisioned(client, session):
    await client.get("/api/v1/me", headers=auth_headers("limits_user"))
    user = await session.scalar(select(User).where(User.auth_id == "limits_user"))
    limit = await session.scalar(select(Limit).where(Limit.user_id == user.id))
    assert limit is not None
    assert limit.daily_loss_cap_cents == 20_000
    assert limit.max_concurrent_contests == 3


async def test_second_login_does_not_regrant(client, session):
    await client.get("/api/v1/me", headers=auth_headers("repeat"))
    await client.get("/api/v1/me", headers=auth_headers("repeat"))

    wallet = await _wallet_for(session, "repeat")
    assert wallet.available_cents == 100_000  # still exactly one grant

    count = await session.scalar(
        select(func.count())
        .select_from(Wallet)
        .join(User, User.id == Wallet.user_id)
        .where(User.auth_id == "repeat")
    )
    assert count == 1


async def test_global_solvency_after_provisioning(client, session):
    for sub in ("solv_a", "solv_b", "solv_c"):
        await client.get("/api/v1/me", headers=auth_headers(sub))

    user_total = await session.scalar(
        select(func.coalesce(func.sum(Wallet.available_cents + Wallet.escrow_cents), 0))
    )
    promo = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.account == "platform:promo"
        )
    )
    rake = await session.scalar(
        select(func.coalesce(func.sum(PlatformLedgerEntry.amount_cents), 0)).where(
            PlatformLedgerEntry.account == "platform:rake"
        )
    )
    # sum(available + escrow) == promo_funding − rake, where promo_funding == −promo.
    assert user_total == -promo - rake
    assert user_total == 300_000
