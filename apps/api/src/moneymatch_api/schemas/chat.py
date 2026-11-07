"""Chat wire types — conversations, messages, and invite cards. Requests carry **ids,
a body, and a preset choice only**: the server owns entry cents, timestamps,
invite state, and every derived label.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..models.chat import MAX_MESSAGE_CHARS


class MessageView(BaseModel):
    """One rendered message."""

    id: UUID
    conversation_id: UUID
    sender_id: UUID | None
    sender_username: str | None
    mine: bool
    kind: str
    body: str | None
    payload: dict
    created_at: datetime


class ConversationView(BaseModel):
    """A row in the conversation list (and the header of an open thread)."""

    id: UUID
    kind: str
    title: str
    peer_user_id: UUID | None
    peer_username: str | None
    online: bool
    unread: int
    last_message_at: datetime | None
    last_message_preview: str | None


class ConversationsResponse(BaseModel):
    unread_total: int
    conversations: list[ConversationView]


class ThreadResponse(BaseModel):
    conversation: ConversationView
    messages: list[MessageView]


class OpenConversationRequest(BaseModel):
    """Open (or reopen) a thread: a friend's `user_id` for a DM, or `kind='support'`
    for the support thread.
    """

    user_id: UUID | None = None
    kind: str = "dm"


class InviteDraft(BaseModel):
    """The client's half of an invite card. Entry is a preset choice — the server
    validates it against the offered presets and owns the cents.
    """

    invite_kind: str
    game: str
    entry_preset_cents: int
    metric: str | None = None
    difficulty: str | None = None


class SendMessageRequest(BaseModel):
    """Either a typed line or an invite card (exactly one of the two)."""

    body: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    invite: InviteDraft | None = None


class RespondInviteRequest(BaseModel):
    action: str


class RespondInviteResponse(BaseModel):
    message: MessageView
    match_id: UUID | None = None
    redirect_path: str | None = None


class ChatReadResponse(BaseModel):
    """Named apart from the notifications mark-read so the two never collide in the
    generated OpenAPI component map.
    """

    unread_total: int
