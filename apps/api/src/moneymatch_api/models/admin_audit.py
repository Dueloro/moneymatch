"""Admin audit log (01-architecture §2 · Social & ops).

Every admin action lands here — an append-only trail for disputes and ops.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin, uuid_pk


class AdminAudit(Base, TimestampMixin):
    __tablename__ = "admin_audit"

    id = uuid_pk()
    admin_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
