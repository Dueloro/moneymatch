"""Web Push subscriptions — a browser endpoint + keys we push notifications to.

One row per (user, browser endpoint). The `endpoint` is globally unique (it's the
push service URL for that browser install), so re-subscribing upserts. A 404/410
from the push service on send means the subscription is dead and is pruned.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk


class PushSubscription(Base, TimestampMixin):
    __tablename__ = "push_subscriptions"

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The push service URL for this browser install (globally unique).
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # The subscription's public key + auth secret (base64url), from the browser.
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
