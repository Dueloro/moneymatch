"""Web push: subscribe, emit fans out, dead subscriptions are pruned."""

from __future__ import annotations

from sqlalchemy import func, select

from moneymatch_api.config import get_settings
from moneymatch_api.models.push import PushSubscription
from moneymatch_api.services import notifications_service, push_service

from .factories import create_user


def _enable_vapid(monkeypatch):
    monkeypatch.setattr(get_settings(), "vapid_public_key", "pub")
    monkeypatch.setattr(get_settings(), "vapid_private_key", "priv")


async def _count(session, user_id):
    return await session.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id == user_id)
    )


async def test_emit_pushes_to_subscription(session, monkeypatch):
    _enable_vapid(monkeypatch)
    sent = []
    monkeypatch.setattr(push_service, "_send_one", lambda info, data: sent.append(info))

    user = await create_user(session)
    await push_service.subscribe(
        session, user.id, endpoint="https://push/ep1", p256dh="k", auth="a"
    )
    # A pushable notification fans out to the browser subscription.
    await notifications_service.emit(session, user.id, "settled", {"match_id": "m"})
    assert len(sent) == 1 and sent[0]["endpoint"] == "https://push/ep1"


async def test_non_push_kind_is_in_app_only(session, monkeypatch):
    _enable_vapid(monkeypatch)
    sent = []
    monkeypatch.setattr(push_service, "_send_one", lambda info, data: sent.append(info))
    user = await create_user(session)
    await push_service.subscribe(
        session, user.id, endpoint="https://push/ep2", p256dh="k", auth="a"
    )
    await notifications_service.emit(session, user.id, "refund", {})  # not in copy map
    assert sent == []


async def test_dead_subscription_is_pruned(session, monkeypatch):
    _enable_vapid(monkeypatch)

    class _Resp:
        status_code = 410

    class _Gone(Exception):
        response = _Resp()

    def _raise(info, data):
        raise _Gone()

    monkeypatch.setattr(push_service, "_send_one", _raise)
    user = await create_user(session)
    await push_service.subscribe(
        session, user.id, endpoint="https://push/ep3", p256dh="k", auth="a"
    )
    assert await _count(session, user.id) == 1
    await notifications_service.emit(session, user.id, "settled", {})
    # A 410 Gone means the browser dropped the subscription → we prune it.
    assert await _count(session, user.id) == 0


async def test_subscribe_upserts_by_endpoint(session):
    user = await create_user(session)
    await push_service.subscribe(
        session, user.id, endpoint="https://push/dup", p256dh="k1", auth="a1"
    )
    await push_service.subscribe(
        session, user.id, endpoint="https://push/dup", p256dh="k2", auth="a2"
    )
    assert await _count(session, user.id) == 1
    row = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == "https://push/dup")
    )
    assert row.p256dh == "k2"
