"""Inbox wire types: notification rows + unread count."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationItem(BaseModel):
    id: UUID
    kind: str
    payload: dict
    read: bool
    created_at: datetime


class NotificationsResponse(BaseModel):
    unread: int
    items: list[NotificationItem]


class MarkReadRequest(BaseModel):
    """Mark specific notifications read, or all of them when `ids` is omitted."""

    ids: list[UUID] | None = None


class MarkReadResponse(BaseModel):
    unread: int
